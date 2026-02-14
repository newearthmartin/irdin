import time
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand

from palestras.models import Palestra

BASE_URL = "https://www.irdin.org.br/site/categoria-produto/palestras/"


class Command(BaseCommand):
    help = "Scrape product URLs from listing pages"

    def add_arguments(self, parser):
        parser.add_argument(
            "--start-page", type=int, default=1, help="Page number to start from"
        )
        parser.add_argument(
            "--delay", type=float, default=1.0, help="Delay between requests in seconds"
        )

    def handle(self, *args, **options):
        start_page = options["start_page"]
        delay = options["delay"]
        page = start_page
        total_created = 0

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            while True:
                if page == 1:
                    url = BASE_URL
                else:
                    url = f"{BASE_URL}page/{page}/"

                self.stdout.write(f"Fetching page {page}: {url}")

                try:
                    resp = client.get(url)
                except httpx.HTTPError as e:
                    self.stderr.write(f"HTTP error on page {page}: {e}")
                    break

                if resp.status_code == 404:
                    self.stdout.write(f"Page {page} returned 404, stopping.")
                    break

                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "lxml")

                # Extract product URLs from the listing grid
                product_links = soup.select("h3.wd-entities-title a")
                if not product_links:
                    # Try alternate selector
                    product_links = soup.select(".product a.product-image-link")

                if not product_links:
                    self.stdout.write(f"No products found on page {page}, stopping.")
                    break

                created_on_page = 0
                for link in product_links:
                    href = link.get("href", "")
                    if not href or "/produtos/" not in href:
                        continue

                    full_url = urljoin(BASE_URL, href)
                    # Extract slug from URL: /produtos/<slug>/
                    slug = full_url.rstrip("/").split("/")[-1]

                    _, created = Palestra.objects.get_or_create(
                        slug=slug, defaults={"url": full_url}
                    )
                    if created:
                        created_on_page += 1

                total_created += created_on_page
                self.stdout.write(
                    f"  Found {len(product_links)} products, "
                    f"created {created_on_page} new ({total_created} total new)"
                )

                page += 1
                time.sleep(delay)

        total = Palestra.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created {total_created} new records. "
                f"Total palestras in DB: {total}"
            )
        )
