from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from palestras.models import Author

HEADERS = {
    "User-Agent": "irdin-scraper/1.0 (https://github.com/irdin; contact@irdin) httpx/0.28"
}


class Command(BaseCommand):
    help = "Fetch author profile photos from IRDIN website or Wikipedia"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit", type=int, default=0, help="Max authors to process (0=all)"
        )
        parser.add_argument(
            "--refetch",
            action="store_true",
            help="Re-fetch even if photo already set",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        refetch = options["refetch"]

        qs = Author.objects.all()
        if not refetch:
            qs = qs.filter(photo="")
        if limit:
            qs = qs[:limit]

        authors = list(qs)
        self.stdout.write(f"Found {len(authors)} authors to process")

        for i, author in enumerate(authors, 1):
            self.stdout.write(f"[{i}/{len(authors)}] {author.name}")
            try:
                search_name = author.wikipedia_search or author.name
                img_bytes = self._fetch_from_wikipedia(search_name)
                if img_bytes:
                    author.photo.save(
                        f"{author.slug}.jpg",
                        ContentFile(img_bytes),
                        save=True,
                    )
                    self.stdout.write(
                        self.style.SUCCESS(f"  -> saved {len(img_bytes)} bytes")
                    )
                else:
                    self.stdout.write("  -> no photo found")
            except Exception as e:
                self.stderr.write(f"  Error: {e}")

        total_with = Author.objects.exclude(photo="").count()
        total = Author.objects.count()
        self.stdout.write(
            self.style.SUCCESS(f"Done. Authors with photos: {total_with}/{total}")
        )

    def _fetch_from_irdin(self, author):
        """Try to find author photo on IRDIN website via a palestra page."""
        palestra = author.palestra_set.first()
        if not palestra:
            return None

        try:
            resp = httpx.get(palestra.url, timeout=15, follow_redirects=True)
            resp.raise_for_status()
        except Exception as e:
            self.stderr.write(f"  IRDIN palestra fetch error: {e}")
            return None

        soup = BeautifulSoup(resp.text, "lxml")

        # Find author link in the info table
        author_link = None
        for th in soup.find_all("th"):
            if "Autor" in th.get_text():
                td = th.find_next_sibling("td")
                if td:
                    for a in td.find_all("a", href=True):
                        if author.slug in a["href"] or author.name in a.get_text():
                            author_link = a["href"]
                            break
                break

        if not author_link:
            return None

        try:
            resp2 = httpx.get(author_link, timeout=15, follow_redirects=True)
            resp2.raise_for_status()
        except Exception as e:
            self.stderr.write(f"  IRDIN author page fetch error: {e}")
            return None

        soup2 = BeautifulSoup(resp2.text, "lxml")

        def get_img_url(img):
            """Return real URL from img tag, preferring data-src over src (lazy loading)."""
            url = img.get("data-src") or img.get("src", "")
            return url if url and not url.startswith("data:") else None

        # Try various selectors for profile image
        img_url = None
        for selector in [
            "img.wp-post-image",
            "img.attachment-full",
            "img.attachment-large",
            "img.attachment-medium",
        ]:
            img = soup2.select_one(selector)
            if img:
                img_url = get_img_url(img)
                if img_url:
                    break

        # Fallback: first usable img in main content area
        if not img_url:
            for container in ["main", "article", ".entry-content", ".page-content", "#content"]:
                area = soup2.select_one(container)
                if area:
                    for img in area.find_all("img"):
                        img_url = get_img_url(img)
                        if img_url and not img_url.endswith(".gif"):
                            break
                    if img_url:
                        break

        if not img_url:
            return None

        # Resolve relative URLs against the author page URL
        img_url = urljoin(str(resp2.url), img_url)
        return self._download_image(img_url)

    def _fetch_from_wikipedia(self, name):
        """Try pt.wikipedia then en.wikipedia for an author photo."""
        for lang in ("pt", "en"):
            img_bytes = self._wikipedia_photo(name, lang)
            if img_bytes:
                return img_bytes
        return None

    def _wikipedia_photo(self, name, lang):
        base = f"https://{lang}.wikipedia.org"

        # Step 1: try direct page title lookup (exact match)
        src = self._wikipedia_summary_photo(base, name, name, lang)
        if src:
            return self._download_image(src)

        # Step 2: full-text search, but validate that the result title
        # is a close match (all significant name words appear in the title)
        search_url = (
            f"{base}/w/api.php?action=query&list=search"
            f"&srsearch={quote(name)}&format=json&srlimit=5"
        )
        try:
            resp = httpx.get(search_url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            hits = resp.json().get("query", {}).get("search", [])
        except Exception as e:
            self.stderr.write(f"  Wikipedia {lang} search error: {e}")
            return None

        name_lower = name.lower()
        for hit in hits:
            title = hit["title"]
            title_lower = title.lower()
            # Title must start with the author name (allows "Name (disambiguation)")
            if not title_lower.startswith(name_lower):
                continue
            src = self._wikipedia_summary_photo(base, title, name, lang)
            if src:
                return self._download_image(src)

        return None

    def _wikipedia_summary_photo(self, base, title, name, lang):
        """Fetch page summary and return thumbnail URL if page is valid."""
        summary_url = f"{base}/api/rest_v1/page/summary/{quote(title)}"
        try:
            resp = httpx.get(summary_url, headers=HEADERS, timeout=10)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            if data.get("type") in ("disambiguation", "no-extract"):
                return None
            thumbnail = data.get("thumbnail", {})
            src = thumbnail.get("source")
            if src:
                self.stdout.write(f"  -> Wikipedia ({lang}): {data['title']}")
            return src
        except Exception as e:
            self.stderr.write(f"  Wikipedia {lang} summary error ({title}): {e}")
            return None

    def _download_image(self, url):
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "image" not in content_type:
                return None
            return resp.content
        except Exception as e:
            self.stderr.write(f"  Image download error: {e}")
            return None
