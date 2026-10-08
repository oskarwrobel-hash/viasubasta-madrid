#!/usr/bin/env python3
"""
Viasubasta Madrid public catalogue scraper.

Designed to:
- discover pagination
- collect auction links
- extract common listing fields
- download publicly exposed images
- maintain data/auctions.json

No login/CAPTCHA/access-control bypassing is implemented.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.viasubasta.com"
CATALOGUE = f"{BASE}/subastas-madrid/"
DATA_DIR = Path("data")
IMAGE_DIR = DATA_DIR / "images"
DB_FILE = DATA_DIR / "auctions.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MadridAuctionCatalogue/1.0; +https://github.com/)"
}

session = requests.Session()
session.headers.update(HEADERS)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def get(url: str, timeout: int = 30):
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response


def canonical(url: str) -> str:
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, p.path.rstrip("/"), "", p.query, ""))


def same_site(url: str) -> bool:
    return urlparse(url).netloc.endswith("viasubasta.com")


def discover_catalogue_pages(max_pages: int | None = None) -> list[str]:
    pages = []
    seen = set()

    # Start with the known catalogue URL and follow pagination links.
    queue = [CATALOGUE]

    while queue:
        url = canonical(queue.pop(0))
        if url in seen:
            continue
        seen.add(url)
        pages.append(url)

        if max_pages and len(pages) >= max_pages:
            break

        try:
            html = get(url).text
        except Exception as exc:
            print(f"[WARN] Could not read {url}: {exc}", file=sys.stderr)
            continue

        soup = BeautifulSoup(html, "lxml")

        candidates = []
        for a in soup.find_all("a", href=True):
            href = canonical(urljoin(url, a["href"]))
            if not same_site(href):
                continue
            if "/subastas-madrid" not in urlparse(href).path:
                continue
            # Pagination links generally have ?page=N.
            if "page=" in urlparse(href).query:
                candidates.append(href)

        for href in candidates:
            if href not in seen and href not in queue:
                queue.append(href)

        time.sleep(0.5)

    return pages


def extract_listing_links(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links = []

    # Prefer links that are inside listing cards/containers, but fall back
    # to any same-site link that is not another catalogue page.
    for a in soup.find_all("a", href=True):
        href = canonical(urljoin(page_url, a["href"]))
        path = urlparse(href).path

        if not same_site(href):
            continue
        if "/subastas-madrid" in path:
            continue
        if href == BASE:
            continue

        text = clean(a.get_text(" ", strip=True))
        # Listing links usually contain a reference/title or point to a lot.
        if text or any(x in path.lower() for x in ("/subasta", "/lote", "/auction")):
            links.append(href)

    # Preserve order and remove duplicates.
    result = []
    seen = set()
    for x in links:
        if x not in seen:
            seen.add(x)
            result.append(x)
    return result


def first_text(soup: BeautifulSoup, selectors: list[str]) -> str:
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            value = clean(node.get_text(" ", strip=True))
            if value:
                return value
    return ""


def extract_reference(soup: BeautifulSoup, url: str) -> str:
    text = soup.get_text(" ", strip=True)
    patterns = [
        r"(?:Ref(?:erencia)?\.?\s*|Referencia\s*#?\s*)(\d+)",
        r"(?:Subasta\s*#?\s*)(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1)

    nums = re.findall(r"\d{3,}", url)
    return nums[-1] if nums else hashlib.sha1(url.encode()).hexdigest()[:12]


def parse_price(text: str) -> float | None:
    if not text:
        return None
    # Find euro-like amounts.
    matches = re.findall(r"(?:€\s*)?(\d[\d.\s]*)(?:,\d{1,2})?\s*€?", text)
    for raw in matches:
        raw = raw.replace(".", "").replace(" ", "")
        if raw.isdigit():
            value = float(raw)
            if value < 100_000_000:
                return value
    return None


def extract_images(soup: BeautifulSoup, page_url: str) -> list[str]:
    urls = []

    def add(value):
        if not value:
            return
        value = value.strip()
        if value.startswith("data:"):
            return
        full = urljoin(page_url, value)
        if urlparse(full).scheme in ("http", "https"):
            urls.append(full)

    # OpenGraph
    for meta in soup.find_all("meta"):
        prop = meta.get("property") or meta.get("name")
        if prop and prop.lower() in {"og:image", "twitter:image"}:
            add(meta.get("content"))

    # JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        for match in re.findall(r'"(?:image|contentUrl)"\s*:\s*"([^"]+)"', raw):
            add(match.replace("\\/", "/"))

    # Normal images / lazy-loaded images
    for img in soup.find_all("img"):
        for attr in ("src", "data-src", "data-lazy-src", "data-original"):
            add(img.get(attr))
        srcset = img.get("srcset")
        if srcset:
            add(srcset.split(",")[0].strip().split(" ")[0])

    # Deduplicate while preserving order.
    out = []
    seen = set()
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def extract_auction(url: str) -> dict:
    html = get(url).text
    soup = BeautifulSoup(html, "lxml")

    title = first_text(soup, [
        "h1", ".title", ".auction-title", ".product-title",
        "[class*='title']"
    ])

    if not title and soup.title:
        title = clean(soup.title.get_text())

    page_text = clean(soup.get_text(" ", strip=True))

    status = ""
    for word in ("ACTIVA", "ACTIVO", "FINALIZADA", "FINALIZADO",
                 "PRÓXIMAMENTE", "PROXIMAMENTE", "CERRADA", "CERRADO"):
        if word.lower() in page_text.lower():
            status = word.lower()
            break

    bid_text = ""
    for selector in [
        ".highest-bid", ".current-bid", ".bid", "[class*='bid']",
        "[class*='precio']", "[class*='price']"
    ]:
        node = soup.select_one(selector)
        if node:
            bid_text = clean(node.get_text(" ", strip=True))
            if bid_text:
                break

    current_bid = parse_price(bid_text) or parse_price(page_text)

    images = extract_images(soup, url)
    reference = extract_reference(soup, url)

    return {
        "id": reference,
        "reference": reference,
        "title": title,
        "status": status or "unknown",
        "current_bid": current_bid,
        "currency": "EUR",
        "url": url,
        "image_urls": images,
        "image": None,
        "images": [],
        "first_seen": None,
        "last_seen": now_iso(),
    }


def load_db() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DB_FILE.exists():
        return {}
    try:
        return json.loads(DB_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_db(db: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DB_FILE.write_text(
        json.dumps(db, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def safe_extension(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return suffix
    return ".jpg"


def download_image(url: str, destination: Path) -> bool:
    try:
        r = get(url, timeout=30)
        content_type = r.headers.get("content-type", "").lower()
        if not content_type.startswith("image/") and not destination.suffix:
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(r.content)
        return True
    except Exception as exc:
        print(f"[WARN] image {url}: {exc}", file=sys.stderr)
        return False


def update_images(record: dict, all_images: bool):
    urls = record.get("image_urls", [])
    if not urls:
        return

    folder = IMAGE_DIR / str(record["id"])
    downloaded = []

    targets = urls if all_images else urls[:1]

    for index, url in enumerate(targets, 1):
        ext = safe_extension(url)
        filename = "cover" + ext if index == 1 else f"{index:02d}" + ext
        path = folder / filename

        if not path.exists():
            download_image(url, path)

        if path.exists():
            rel = str(path.relative_to(DATA_DIR)).replace("\\", "/")
            downloaded.append(rel)

    if downloaded:
        record["images"] = downloaded
        record["image"] = downloaded[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--max-listings", type=int, default=None)
    parser.add_argument("--download-images", action="store_true")
    parser.add_argument("--all-images", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"Source: {CATALOGUE}")

    pages = discover_catalogue_pages(args.max_pages)
    print(f"Catalogue pages discovered: {len(pages)}")

    listing_urls = []
    seen = set()

    for page in pages:
        try:
            html = get(page).text
            links = extract_listing_links(html, page)
            for link in links:
                if link not in seen:
                    seen.add(link)
                    listing_urls.append(link)
                    if args.max_listings and len(listing_urls) >= args.max_listings:
                        break
        except Exception as exc:
            print(f"[WARN] {page}: {exc}", file=sys.stderr)

        if args.max_listings and len(listing_urls) >= args.max_listings:
            break
        time.sleep(0.5)

    print(f"Listing URLs discovered: {len(listing_urls)}")

    db = load_db()
    timestamp = now_iso()

    for i, url in enumerate(listing_urls, 1):
        print(f"[{i}/{len(listing_urls)}] {url}")
        try:
            record = extract_auction(url)
            old = db.get(record["id"], {})

            record["first_seen"] = old.get("first_seen") or timestamp

            if old.get("images") and not record.get("images"):
                record["images"] = old["images"]
                record["image"] = old.get("image")

            if args.download_images:
                update_images(record, args.all_images)

            # Keep historical source image URLs useful for diagnostics.
            db[record["id"]] = record

        except Exception as exc:
            print(f"[WARN] listing failed: {exc}", file=sys.stderr)

        time.sleep(0.75)

    # Preserve disappeared listings instead of deleting them.
    current_ids = {str(x) for x in [db[k]["id"] for k in db]}
    for key, record in db.items():
        if record.get("last_seen") != timestamp and record.get("status") != "not_seen":
            # Do not overwrite fresh status; mark only records not found in
            # this run by comparing their last_seen timestamp.
            if record.get("last_seen") != timestamp:
                record["status_previous"] = record.get("status")
                record["status"] = "not_seen"

    if args.dry_run:
        print("Dry run: no database written.")
        return

    save_db(db)
    print(f"Saved {len(db)} records to {DB_FILE}")


if __name__ == "__main__":
    main()
