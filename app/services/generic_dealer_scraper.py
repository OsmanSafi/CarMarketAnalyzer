import json
import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag


USER_AGENT = "CarMarketAnalyzer/0.1 (public vehicle market research)"

VIN_PATTERN = re.compile(
    r"\b[A-HJ-NPR-Z0-9]{17}\b",
    re.IGNORECASE,
)

YEAR_PATTERN = re.compile(r"\b(19[8-9]\d|20[0-3]\d)\b")

PRICE_PATTERN = re.compile(r"\$\s*([\d,]{4,})")

MILEAGE_PATTERNS = [
    re.compile(
        r"Mileage\s*[:\-]?\s*"
        r"([\d,]+)\s*(?:Miles?|mi\b)",
        re.IGNORECASE,
    ),
    re.compile(
        r"([\d,]+)\s*(?:Miles?|mi\b)",
        re.IGNORECASE,
    ),
]


@dataclass
class ScrapedListing:
    provider: str
    source_site: str
    page_url: str

    vin: str | None = None
    year: int | None = None

    make: str | None = None
    model: str | None = None
    trim: str | None = None

    price: float | None = None
    mileage: int | None = None

    dealer: str | None = None
    city: str | None = None
    state: str | None = None

    title: str | None = None

    extraction_method: str | None = None
    data_quality: float | None = None

    def to_dict(
        self,
    ) -> dict:
        return asdict(self)


class GenericDealerScraper:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.timeout_seconds = timeout_seconds

        self.headers = {
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": ("en-US,en;q=0.8"),
        }

    async def scrape(
        self,
        url: str,
    ) -> list[ScrapedListing]:
        self._validate_url(url)

        allowed = await self._robots_allowed(url)

        if not allowed:
            raise PermissionError(
                ("robots.txt does not allow this page to be fetched.")
            )

        async with httpx.AsyncClient(
            headers=self.headers,
            timeout=self.timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)

            response.raise_for_status()

        final_url = str(response.url)

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        listings = self._extract_json_ld(
            soup=soup,
            page_url=final_url,
        )

        if listings:
            return self._deduplicate(listings)

        listings = self._extract_html_cards(
            soup=soup,
            page_url=final_url,
        )

        return self._deduplicate(listings)

    # --------------------------------------------------
    # URL / ROBOTS
    # --------------------------------------------------

    def _validate_url(
        self,
        url: str,
    ) -> None:
        parsed = urlparse(url)

        if parsed.scheme not in {
            "http",
            "https",
        }:
            raise ValueError(("Only HTTP and HTTPS URLs are supported."))

        if not parsed.hostname:
            raise ValueError("Invalid URL.")

        hostname = parsed.hostname.strip().lower()

        blocked_hosts = {
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "::1",
        }

        if hostname in blocked_hosts:
            raise ValueError(("Local/private URLs are not supported."))

    async def _robots_allowed(
        self,
        url: str,
    ) -> bool:
        parsed = urlparse(url)

        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        parser = RobotFileParser()
        parser.set_url(robots_url)

        try:
            async with httpx.AsyncClient(
                headers=self.headers,
                timeout=10.0,
                follow_redirects=True,
            ) as client:
                response = await client.get(robots_url)

            # No robots.txt generally
            # means there are no robots
            # directives to apply.
            if response.status_code == 404:
                return True

            if response.status_code >= 400:
                return False

            parser.parse(response.text.splitlines())

            return parser.can_fetch(
                USER_AGENT,
                url,
            )

        except httpx.HTTPError:
            # Fail closed when robots
            # status cannot be verified.
            return False

    # --------------------------------------------------
    # JSON-LD
    # --------------------------------------------------

    def _extract_json_ld(
        self,
        soup: BeautifulSoup,
        page_url: str,
    ) -> list[ScrapedListing]:
        results: list[ScrapedListing] = []

        scripts = soup.find_all(
            "script",
            attrs={"type": ("application/ld+json")},
        )

        for script in scripts:
            content = script.string or script.get_text()

            if not content:
                continue

            try:
                payload = json.loads(content)
            except (
                json.JSONDecodeError,
                TypeError,
            ):
                continue

            objects = self._flatten_json_ld(payload)

            for item in objects:
                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                if not (self._looks_like_vehicle(item)):
                    continue

                listing = self._listing_from_json_ld(
                    item=item,
                    page_url=(page_url),
                )

                if listing:
                    results.append(listing)

        return results

    def _flatten_json_ld(
        self,
        value: Any,
    ) -> list[dict]:
        results: list[dict] = []

        if isinstance(
            value,
            list,
        ):
            for item in value:
                results.extend(self._flatten_json_ld(item))

            return results

        if not isinstance(
            value,
            dict,
        ):
            return results

        graph = value.get("@graph")

        if graph:
            results.extend(self._flatten_json_ld(graph))

        results.append(value)

        return results

    def _looks_like_vehicle(
        self,
        item: dict,
    ) -> bool:
        object_type = item.get("@type")

        if isinstance(
            object_type,
            list,
        ):
            types = {str(value).strip().lower() for value in object_type}

        else:
            types = {str(object_type or "").strip().lower()}

        vehicle_types = {
            "vehicle",
            "car",
            "product",
            "automotivebusiness",
        }

        if types & vehicle_types:
            vin = self._extract_json_vin(item)

            name = str(
                item.get(
                    "name",
                    "",
                )
            )

            return bool(vin or YEAR_PATTERN.search(name))

        return False

    def _listing_from_json_ld(
        self,
        item: dict,
        page_url: str,
    ) -> ScrapedListing | None:
        vin = self._extract_json_vin(item)

        title = self._string_value(item.get("name"))

        year = self._extract_year(
            item,
            title,
        )

        make = (
            self._brand_value(item.get("brand"))
            or self._brand_value(item.get("manufacturer"))
            or self._string_value(item.get("make"))
        )

        model = self._string_value(item.get("model"))

        trim = self._first_string(
            item,
            [
                "vehicleConfiguration",
                "trim",
                "vehicleTrim",
                "configuration",
            ],
        )

        price = self._extract_json_price(item)

        mileage = self._extract_json_mileage(item)

        dealer = None
        city = None
        state = None

        seller = item.get("seller")

        if isinstance(
            seller,
            dict,
        ):
            dealer = self._string_value(seller.get("name"))

            (
                city,
                state,
            ) = self._extract_address(seller.get("address"))

        listing_url = self._string_value(item.get("url")) or page_url

        if listing_url:
            listing_url = urljoin(
                page_url,
                listing_url,
            )

        if not vin:
            vin = self._vin_from_text(
                " ".join(
                    [
                        title or "",
                        json.dumps(item),
                    ]
                )
            )

        if not vin and not price and not mileage:
            return None

        host = urlparse(page_url).netloc.lower()

        quality = 0.70

        if vin:
            quality += 0.10

        if price:
            quality += 0.08

        if mileage is not None:
            quality += 0.05

        if year and (make or model):
            quality += 0.05

        quality = min(
            quality,
            0.98,
        )

        return ScrapedListing(
            provider=("Dealer Website"),
            source_site=host,
            page_url=(listing_url or page_url),
            vin=vin,
            year=year,
            make=make,
            model=model,
            trim=trim,
            price=price,
            mileage=mileage,
            dealer=dealer,
            city=city,
            state=state,
            title=title,
            extraction_method=("json_ld"),
            data_quality=round(
                quality,
                2,
            ),
        )

    def _extract_json_vin(
        self,
        item: dict,
    ) -> str | None:
        possible = [
            item.get("vehicleIdentificationNumber"),
            item.get("vin"),
            item.get("sku"),
            item.get("productID"),
        ]

        for value in possible:
            vin = self._vin_from_text(self._string_value(value) or "")

            if vin:
                return vin

        return None

    def _extract_json_price(
        self,
        item: dict,
    ) -> float | None:
        direct_price = self._money_value(item.get("price"))

        if direct_price:
            return direct_price

        offers = item.get("offers")

        offer_items: list[dict] = []

        if isinstance(
            offers,
            dict,
        ):
            offer_items = [offers]

        elif isinstance(
            offers,
            list,
        ):
            offer_items = [
                offer
                for offer in offers
                if isinstance(
                    offer,
                    dict,
                )
            ]

        for offer in offer_items:
            for key in [
                "price",
                "lowPrice",
                "highPrice",
            ]:
                value = self._money_value(offer.get(key))

                if value:
                    return value

        return None

    def _extract_json_mileage(
        self,
        item: dict,
    ) -> int | None:
        possible = [
            item.get("mileageFromOdometer"),
            item.get("mileage"),
            item.get("odometer"),
        ]

        for value in possible:
            if isinstance(
                value,
                dict,
            ):
                value = value.get("value") or value.get("@value")

            mileage = self._integer_value(value)

            if mileage is not None:
                return mileage

        return None

    # --------------------------------------------------
    # GENERIC HTML CARD FALLBACK
    # --------------------------------------------------

    def _extract_html_cards(
        self,
        soup: BeautifulSoup,
        page_url: str,
    ) -> list[ScrapedListing]:
        results: list[ScrapedListing] = []

        seen_vins: set[str] = set()

        for text_node in soup.find_all(string=VIN_PATTERN):
            vin = self._vin_from_text(str(text_node))

            if not vin or vin in seen_vins:
                continue

            tag = (
                text_node.parent
                if isinstance(
                    text_node.parent,
                    Tag,
                )
                else None
            )

            if not tag:
                continue

            container = self._find_vehicle_container(
                tag=tag,
                vin=vin,
            )

            if not container:
                continue

            listing = self._listing_from_html_container(
                container=container,
                vin=vin,
                page_url=page_url,
            )

            if listing:
                seen_vins.add(vin)

                results.append(listing)

        # Some sites place VINs only
        # inside attributes.
        for tag in soup.find_all(True):
            if not isinstance(
                tag,
                Tag,
            ):
                continue

            attribute_text = " ".join(self._attribute_strings(tag))

            vin = self._vin_from_text(attribute_text)

            if not vin or vin in seen_vins:
                continue

            container = self._find_vehicle_container(
                tag=tag,
                vin=vin,
            )

            if not container:
                continue

            listing = self._listing_from_html_container(
                container=container,
                vin=vin,
                page_url=page_url,
            )

            if listing:
                seen_vins.add(vin)

                results.append(listing)

        return results

    def _find_vehicle_container(
        self,
        tag: Tag,
        vin: str,
    ) -> Tag | None:
        current: Tag | None = tag

        best: Tag | None = None

        for _ in range(8):
            if current is None:
                break

            text = current.get_text(
                " ",
                strip=True,
            )

            if vin in text and len(text) >= 50:
                has_price = bool(PRICE_PATTERN.search(text))

                has_year = bool(YEAR_PATTERN.search(text))

                if has_price and has_year:
                    best = current

                    if len(text) <= 2500:
                        return current

            parent = current.parent

            current = (
                parent
                if isinstance(
                    parent,
                    Tag,
                )
                else None
            )

        return best

    def _listing_from_html_container(
        self,
        container: Tag,
        vin: str,
        page_url: str,
    ) -> ScrapedListing | None:
        text = container.get_text(
            " ",
            strip=True,
        )

        title = self._extract_html_title(
            container,
            text,
        )

        year = self._year_from_text(title or text)

        price = self._price_from_text(text)

        mileage = self._mileage_from_text(text)

        listing_url = self._extract_container_url(
            container,
            page_url,
        )

        host = urlparse(page_url).netloc.lower()

        # We deliberately do not guess
        # make/model/trim from arbitrary
        # token positions. VIN decoding
        # can populate those reliably
        # during integration.
        quality = 0.60

        if vin:
            quality += 0.12

        if year:
            quality += 0.05

        if price:
            quality += 0.08

        if mileage is not None:
            quality += 0.07

        quality = min(
            quality,
            0.92,
        )

        return ScrapedListing(
            provider=("Dealer Website"),
            source_site=host,
            page_url=(listing_url or page_url),
            vin=vin,
            year=year,
            price=price,
            mileage=mileage,
            title=title,
            extraction_method=("html_card"),
            data_quality=round(
                quality,
                2,
            ),
        )

    # --------------------------------------------------
    # PARSING HELPERS
    # --------------------------------------------------

    def _extract_html_title(
        self,
        container: Tag,
        text: str,
    ) -> str | None:
        for heading_name in [
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        ]:
            heading = container.find(heading_name)

            if heading:
                value = heading.get_text(
                    " ",
                    strip=True,
                )

                if YEAR_PATTERN.search(value):
                    return value

        year_match = YEAR_PATTERN.search(text)

        if not year_match:
            return None

        start = year_match.start()

        snippet = text[start : start + 140]

        stop_words = [
            "Your Price",
            "Selling Price",
            "Mileage",
            "VIN",
            "Stock",
            "Disclosure",
        ]

        for stop_word in stop_words:
            index = snippet.lower().find(stop_word.lower())

            if index > 0:
                snippet = snippet[:index]

        return snippet.strip(" -|:") or None

    def _price_from_text(
        self,
        text: str,
    ) -> float | None:
        priority_patterns = [
            re.compile(
                (
                    r"Selling Price"
                    r"\s*\$"
                    r"\s*([\d,]+)"
                ),
                re.IGNORECASE,
            ),
            re.compile(
                (
                    r"Sale Price"
                    r"\s*\$"
                    r"\s*([\d,]+)"
                ),
                re.IGNORECASE,
            ),
            re.compile(
                (
                    r"Internet Price"
                    r"\s*\$"
                    r"\s*([\d,]+)"
                ),
                re.IGNORECASE,
            ),
            re.compile(
                (
                    r"Your Price"
                    r"\s*\$"
                    r"\s*([\d,]+)"
                ),
                re.IGNORECASE,
            ),
        ]

        for pattern in priority_patterns:
            match = pattern.search(text)

            if match:
                return self._money_value(match.group(1))

        match = PRICE_PATTERN.search(text)

        if not match:
            return None

        return self._money_value(match.group(1))

    def _mileage_from_text(
        self,
        text: str,
    ) -> int | None:
        for pattern in MILEAGE_PATTERNS:
            match = pattern.search(text)

            if match:
                return self._integer_value(match.group(1))

        return None

    def _extract_container_url(
        self,
        container: Tag,
        page_url: str,
    ) -> str | None:
        links = container.find_all(
            "a",
            href=True,
        )

        for link in links:
            href = str(link.get("href", "")).strip()

            if not href:
                continue

            if (
                "viewdetail" in href.lower()
                or "vehicle" in href.lower()
                or "inventory" in href.lower()
            ):
                return urljoin(
                    page_url,
                    href,
                )

        if links:
            href = links[0].get("href")

            if href:
                return urljoin(
                    page_url,
                    str(href),
                )

        return None

    def _attribute_strings(
        self,
        tag: Tag,
    ) -> list[str]:
        values: list[str] = []

        for value in tag.attrs.values():
            if isinstance(
                value,
                list,
            ):
                values.extend(str(item) for item in value)

            else:
                values.append(str(value))

        return values

    def _extract_year(
        self,
        item: dict,
        title: str | None,
    ) -> int | None:
        possible = [
            item.get("vehicleModelDate"),
            item.get("modelDate"),
            item.get("year"),
        ]

        for value in possible:
            integer = self._integer_value(value)

            if integer and 1980 <= integer <= 2035:
                return integer

        return self._year_from_text(title or "")

    def _year_from_text(
        self,
        value: str,
    ) -> int | None:
        match = YEAR_PATTERN.search(value)

        if not match:
            return None

        return int(match.group(0))

    def _vin_from_text(
        self,
        value: str,
    ) -> str | None:
        match = VIN_PATTERN.search(value)

        if not match:
            return None

        return match.group(0).upper()

    def _money_value(
        self,
        value: Any,
    ) -> float | None:
        if value is None:
            return None

        if isinstance(
            value,
            (
                int,
                float,
            ),
        ):
            amount = float(value)

        else:
            cleaned = re.sub(
                r"[^\d.]",
                "",
                str(value),
            )

            if not cleaned:
                return None

            try:
                amount = float(cleaned)
            except ValueError:
                return None

        if amount <= 0 or amount > 1000000:
            return None

        return amount

    def _integer_value(
        self,
        value: Any,
    ) -> int | None:
        if value is None:
            return None

        cleaned = re.sub(
            r"[^\d]",
            "",
            str(value),
        )

        if not cleaned:
            return None

        try:
            return int(cleaned)

        except ValueError:
            return None

    def _brand_value(
        self,
        value: Any,
    ) -> str | None:
        if isinstance(
            value,
            dict,
        ):
            return self._string_value(value.get("name"))

        return self._string_value(value)

    def _string_value(
        self,
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        if isinstance(
            value,
            str,
        ):
            cleaned = value.strip()

            return cleaned or None

        if isinstance(
            value,
            (
                int,
                float,
            ),
        ):
            return str(value)

        return None

    def _first_string(
        self,
        item: dict,
        keys: list[str],
    ) -> str | None:
        for key in keys:
            value = self._string_value(item.get(key))

            if value:
                return value

        return None

    def _extract_address(
        self,
        value: Any,
    ) -> tuple[
        str | None,
        str | None,
    ]:
        if not isinstance(
            value,
            dict,
        ):
            return (
                None,
                None,
            )

        city = self._string_value(value.get("addressLocality"))

        state = self._string_value(value.get("addressRegion"))

        return (
            city,
            state,
        )

    # --------------------------------------------------
    # DEDUPLICATION
    # --------------------------------------------------

    def _deduplicate(
        self,
        listings: list[ScrapedListing],
    ) -> list[ScrapedListing]:
        by_key: dict[
            str,
            ScrapedListing,
        ] = {}

        without_key: list[ScrapedListing] = []

        for listing in listings:
            if listing.vin:
                key = listing.vin.upper()

            elif listing.page_url:
                key = listing.page_url

            else:
                without_key.append(listing)

                continue

            existing = by_key.get(key)

            if existing is None:
                by_key[key] = listing

                continue

            existing_quality = existing.data_quality or 0

            new_quality = listing.data_quality or 0

            if new_quality > existing_quality:
                by_key[key] = listing

        return list(by_key.values()) + without_key
