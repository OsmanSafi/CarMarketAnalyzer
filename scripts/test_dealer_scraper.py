import asyncio
import json
import sys
from pathlib import Path


# Add project root to Python path so
# imports like "app.services..." work.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(PROJECT_ROOT),
)


from app.services.generic_dealer_scraper import (  # noqa: E402
    GenericDealerScraper,
)


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage:")

        print("python scripts/test_dealer_scraper.py <URL>")

        return

    url = sys.argv[1]

    scraper = GenericDealerScraper()

    try:
        listings = await scraper.scrape(url)

    except Exception as exc:
        print(f"Scrape failed: {exc}")

        return

    print(f"\nFound {len(listings)} listing(s)\n")

    for listing in listings:
        print(
            json.dumps(
                listing.to_dict(),
                indent=2,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
