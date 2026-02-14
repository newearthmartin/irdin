import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone
from django.utils.text import slugify

from palestras.models import AudioTrack, Author, Palestra

_print_lock = threading.Lock()


class Command(BaseCommand):
    help = "Scrape metadata from individual product pages"

    def add_arguments(self, parser):
        parser.add_argument(
            "--delay", type=float, default=0.5, help="Delay between requests in seconds"
        )
        parser.add_argument(
            "--limit", type=int, default=0, help="Max products to scrape (0=all)"
        )
        parser.add_argument(
            "--workers", type=int, default=4, help="Number of parallel threads"
        )

    def handle(self, *args, **options):
        delay = options["delay"]
        limit = options["limit"]
        workers = options["workers"]

        qs = Palestra.objects.filter(scraped_on__isnull=True)
        if limit:
            qs = qs[:limit]

        pending = list(qs)
        total = len(pending)
        self.stdout.write(f"Found {total} unscraped products (workers={workers})")

        done = 0
        errors = 0

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self._scrape_one, palestra, delay): palestra
                for palestra in pending
            }
            for future in as_completed(futures):
                palestra = futures[future]
                try:
                    future.result()
                    done += 1
                except Exception as e:
                    errors += 1
                    with _print_lock:
                        self.stderr.write(f"  Error ({palestra.slug}): {e}")

                with _print_lock:
                    self.stdout.write(f"  [{done + errors}/{total}] done={done} errors={errors}")

        self.stdout.write(self.style.SUCCESS(f"Done. Scraped {done}, errors {errors}."))

    def _scrape_one(self, palestra, delay):
        close_old_connections()

        with _print_lock:
            self.stdout.write(f"  Fetching: {palestra.slug}")

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(palestra.url)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        self._parse_product(palestra, soup)

        palestra.scraped_on = timezone.now()
        palestra.save()

        with _print_lock:
            self.stdout.write(f"  Saved: {palestra.title}")

        time.sleep(delay)

    def _parse_product(self, palestra, soup):
        # Title
        title_el = soup.select_one("h1.product_title") or soup.select_one("h1")
        if title_el:
            palestra.title = title_el.get_text(strip=True)

        # SKU
        sku_el = soup.select_one(".sku")
        if sku_el:
            palestra.sku = sku_el.get_text(strip=True)

        # Description — exclude paragraphs that contain audio tracks
        desc_tab = soup.select_one("#tab-description")
        if desc_tab:
            desc_parts = []
            for p in desc_tab.select("p"):
                if p.select('a[href$=".mp3"]') or p.select(".fap-single-track"):
                    continue
                text = p.get_text(strip=True)
                if text and text.lower() != "faixas:":
                    desc_parts.append(text)
            palestra.description = "\n".join(desc_parts)

        # Categories
        cat_links = soup.select(".posted_in a")
        if cat_links:
            palestra.categories = ", ".join(a.get_text(strip=True) for a in cat_links)

        # Tags
        tag_links = soup.select(".tagged_as a")
        if tag_links:
            palestra.tags = ", ".join(a.get_text(strip=True) for a in tag_links)

        # Additional information table
        info_table = soup.select_one(
            "#tab-additional_information table, "
            ".woocommerce-product-attributes"
        )
        if info_table:
            for row in info_table.select("tr"):
                th = row.select_one("th")
                td = row.select_one("td")
                if not th or not td:
                    continue
                label = th.get_text(strip=True).lower()
                if "peso" in label or "weight" in label:
                    palestra.weight = td.get_text(strip=True)
                elif "dimens" in label:
                    palestra.dimensions = td.get_text(strip=True)
                elif "mídia" in label or "media" in label or "formato" in label:
                    palestra.media_format = td.get_text(strip=True)
                elif "autor" in label or "author" in label:
                    self._parse_authors(palestra, td)

        # Audio tracks — links to .mp3 files
        self._parse_audio_tracks(palestra, soup)

    def _parse_authors(self, palestra, td):
        author_links = td.select("a")
        if author_links:
            names = [a.get_text(strip=True) for a in author_links]
        else:
            names = [n.strip() for n in td.get_text().split(",") if n.strip()]

        for name in names:
            slug = slugify(name)
            if not slug:
                continue
            author, _ = Author.objects.get_or_create(
                slug=slug, defaults={"name": name}
            )
            palestra.authors.add(author)

    def _parse_audio_tracks(self, palestra, soup):
        # Each track has a span.fap-single-track with data-title and data-href
        play_buttons = soup.select("span.fap-single-track[data-href]")
        seen_urls = set()

        for btn in play_buttons:
            mp3_url = btn.get("data-href", "")
            if not mp3_url or mp3_url in seen_urls:
                continue
            seen_urls.add(mp3_url)

            name = btn.get("data-title", "").strip()
            if not name:
                name = mp3_url.rstrip("/").split("/")[-1]

            AudioTrack.objects.get_or_create(
                palestra=palestra,
                mp3_url=mp3_url,
                defaults={"name": name},
            )

        # Fallback: if no play buttons found, try download links
        if not seen_urls:
            for link in soup.select('a.baixar[href$=".mp3"]'):
                mp3_url = link.get("href", "")
                if not mp3_url or mp3_url in seen_urls:
                    continue
                seen_urls.add(mp3_url)

                # Try to get name from adjacent textobaixar span
                text_span = link.find_next_sibling("span", class_="textobaixar")
                name = text_span.get_text(strip=True) if text_span else ""
                if not name:
                    name = mp3_url.rstrip("/").split("/")[-1]

                AudioTrack.objects.get_or_create(
                    palestra=palestra,
                    mp3_url=mp3_url,
                    defaults={"name": name},
                )
