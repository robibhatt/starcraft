#!/usr/bin/env python3
"""
Scrape Liquipedia StarCraft 2 patch timeline into a CSV.

Outputs: ../data/patch_timeline.csv with columns:
  patch_id, build, release_date_na

Uses Liquipedia MediaWiki API for stability vs raw HTML pages.
"""

from __future__ import annotations

import csv
import os
import re
import sys
from dataclasses import dataclass
from datetime import date
from typing import Optional, Iterable

import requests
from bs4 import BeautifulSoup, Tag

try:
    from dateutil import parser as dateparser
except ImportError:
    print("Please install python-dateutil: pip install python-dateutil", file=sys.stderr)
    raise


LIQUIPEDIA_API = "https://liquipedia.net/starcraft2/api.php"
PAGE = "Patches"

# Matches version strings like "4.1.3", "10.0.0.1", "4.0.2 BU"
VERSION_PATTERN = re.compile(r"^(\d+(?:\.\d+){1,3})(?: BU)?$")


@dataclass(frozen=True)
class PatchRow:
    patch_id: str
    build: Optional[str]
    release_date_na: Optional[date]


def _session() -> requests.Session:
    """Create a session with appropriate headers for Liquipedia."""
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "sc2-patch-scraper/1.0 (contact: you@example.com) requests",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return sess


def fetch_portal_html(sess: requests.Session) -> str:
    """Fetch rendered HTML for the Portal:Patches page via MediaWiki API."""
    params = {
        "action": "parse",
        "format": "json",
        "page": PAGE,
        "prop": "text",
        "disablelimitreport": "1",
        "disableeditsection": "1",
        "redirects": "1",
    }
    resp = sess.get(LIQUIPEDIA_API, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"MediaWiki API error: {data['error']}")
    return data["parse"]["text"]["*"]


def _clean_text(text: str) -> str:
    """Normalize whitespace in text."""
    return re.sub(r"\s+", " ", text).strip()


def _parse_date_maybe(text: str) -> Optional[date]:
    """Parse a date string, returning None for invalid/empty/placeholder values."""
    text = _clean_text(text)
    if not text or text.lower() in {"-", "n/a", "na", "unknown"}:
        return None
    try:
        parsed = dateparser.parse(text, fuzzy=True)
        return parsed.date() if parsed else None
    except Exception:
        return None


def _extract_version(text: str) -> Optional[str]:
    """
    Extract version string from patch cell text.

    Handles formats like:
    - "Patch 4.1.3" -> "4.1.3"
    - "Patch 4.0.2 BU" -> "4.0.2 BU"
    - "4.1.3" -> "4.1.3"

    Returns None if no valid version found.
    """
    text = _clean_text(text)

    # Strip "Patch " prefix if present
    if text.lower().startswith("patch "):
        text = text[6:].strip()

    # Check if it matches version pattern
    if VERSION_PATTERN.match(text):
        return text

    return None


def extract_rows_from_table(table: Tag) -> list[PatchRow]:
    """
    Extract patch data from a single table.

    Liquipedia tables have header rows followed by data rows:
    - Header: ['Notes', 'Release date (NA)', 'Build', 'Highlights']
    - Data: Patch name, Date, Build number, Highlights
    """
    rows: list[PatchRow] = []

    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue

        # Skip header rows (first cell is <th>)
        if cells[0].name == "th":
            continue

        # Column 0: Patch version
        patch_text = _clean_text(cells[0].get_text(" "))
        version = _extract_version(patch_text)
        if not version:
            continue

        # Column 1: Date
        release_date = None
        if len(cells) > 1:
            date_text = _clean_text(cells[1].get_text(" "))
            release_date = _parse_date_maybe(date_text)

        # Column 2: Build
        build = None
        if len(cells) > 2:
            build_text = _clean_text(cells[2].get_text(" "))
            if build_text and build_text != "-":
                build = build_text

        rows.append(PatchRow(
            patch_id=version,
            build=build,
            release_date_na=release_date,
        ))

    return rows


def extract_all_rows(soup: BeautifulSoup) -> list[PatchRow]:
    """Extract patch rows from all wikitables in the page."""
    all_rows: list[PatchRow] = []

    for table in soup.find_all("table", class_="wikitable"):
        all_rows.extend(extract_rows_from_table(table))

    return all_rows


def write_csv(rows: Iterable[PatchRow], path: str) -> None:
    """Write patch rows to a CSV file, sorted by release date."""
    sorted_rows = sorted(
        rows,
        key=lambda r: (r.release_date_na or date.min, r.patch_id)
    )

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["patch_id", "build", "release_date_na"])
        for row in sorted_rows:
            writer.writerow([
                row.patch_id,
                row.build or "",
                row.release_date_na.isoformat() if row.release_date_na else "",
            ])


def main() -> None:
    sess = _session()
    html = fetch_portal_html(sess)
    soup = BeautifulSoup(html, "html.parser")
    rows = extract_all_rows(soup)

    if not rows:
        raise RuntimeError(
            "Extracted 0 patch rows. Liquipedia table format may have changed."
        )

    out_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "patch_timeline.csv")

    write_csv(rows, out_path)
    print(f"Wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
