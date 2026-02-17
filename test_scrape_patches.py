#!/usr/bin/env python3
"""Tests for scrape_patches.py"""

import csv
import os
import tempfile
from datetime import date

import pytest
from bs4 import BeautifulSoup

from scrape_patches import (
    PatchRow,
    _clean_text,
    _parse_date_maybe,
    _extract_version,
    extract_rows_from_table,
    extract_all_rows,
    write_csv,
)


# =============================================================================
# Test: _clean_text
# =============================================================================

def test_clean_text_removes_extra_whitespace():
    assert _clean_text("  hello   world  ") == "hello world"


def test_clean_text_handles_newlines():
    assert _clean_text("hello\n\nworld") == "hello world"


def test_clean_text_handles_tabs():
    assert _clean_text("hello\t\tworld") == "hello world"


# =============================================================================
# Test: _parse_date_maybe
# =============================================================================

def test_parse_date_valid_iso():
    assert _parse_date_maybe("2019-11-26") == date(2019, 11, 26)


def test_parse_date_valid_text_format():
    assert _parse_date_maybe("Nov 26, 2019") == date(2019, 11, 26)


def test_parse_date_valid_long_format():
    assert _parse_date_maybe("November 26, 2019") == date(2019, 11, 26)


def test_parse_date_liquipedia_format():
    assert _parse_date_maybe("9 January 2018") == date(2018, 1, 9)


def test_parse_date_returns_none_for_dash():
    assert _parse_date_maybe("-") is None


def test_parse_date_returns_none_for_na():
    assert _parse_date_maybe("n/a") is None
    assert _parse_date_maybe("N/A") is None
    assert _parse_date_maybe("na") is None
    assert _parse_date_maybe("NA") is None


def test_parse_date_returns_none_for_empty():
    assert _parse_date_maybe("") is None


def test_parse_date_returns_none_for_unknown():
    assert _parse_date_maybe("unknown") is None
    assert _parse_date_maybe("Unknown") is None


def test_parse_date_handles_whitespace():
    assert _parse_date_maybe("  2019-11-26  ") == date(2019, 11, 26)


# =============================================================================
# Test: _extract_version
# =============================================================================

def test_extract_version_simple():
    assert _extract_version("Patch 4.1.3") == "4.1.3"


def test_extract_version_with_bu_suffix():
    assert _extract_version("Patch 4.0.2 BU") == "4.0.2 BU"


def test_extract_version_four_parts():
    assert _extract_version("Patch 10.0.0.1") == "10.0.0.1"


def test_extract_version_no_prefix():
    assert _extract_version("4.1.3") == "4.1.3"


def test_extract_version_with_link_text():
    # Sometimes the cell contains link text
    assert _extract_version("Patch 5.0.11") == "5.0.11"


def test_extract_version_invalid_returns_none():
    assert _extract_version("Bug Fixes") is None
    assert _extract_version("Balance Changes") is None
    assert _extract_version("") is None


def test_extract_version_beta_patch():
    # Table 30 has "Patch 17" format (beta patches)
    assert _extract_version("Patch 17") is None  # Not a version string


# =============================================================================
# Test: extract_rows_from_table
# =============================================================================

TABLE_WITH_HEADER_HTML = """
<table class="wikitable">
    <tr>
        <th>Notes</th>
        <th>Release date (NA)</th>
        <th>Build</th>
        <th>Highlights</th>
    </tr>
    <tr>
        <td>Patch 5.0.15</td>
        <td>30 September 2025</td>
        <td>95248</td>
        <td>Bug Fixes</td>
    </tr>
    <tr>
        <td>Patch 5.0.14</td>
        <td>25 November 2024</td>
        <td>93272</td>
        <td>Bug Fixes</td>
    </tr>
</table>
"""


def test_extract_rows_skips_header_row():
    soup = BeautifulSoup(TABLE_WITH_HEADER_HTML, "html.parser")
    table = soup.find("table")
    assert table is not None
    rows = extract_rows_from_table(table)

    # Should have 2 data rows, header row skipped
    assert len(rows) == 2
    assert rows[0].patch_id == "5.0.15"
    assert rows[0].build == "95248"
    assert rows[0].release_date_na == date(2025, 9, 30)
    assert rows[1].patch_id == "5.0.14"


HEADERLESS_TABLE_HTML = """
<table class="wikitable">
    <tr>
        <td>Patch 4.1.3</td>
        <td>9 January 2018</td>
        <td>61021</td>
        <td>Bug Fixes</td>
    </tr>
    <tr>
        <td>Patch 4.1.2</td>
        <td>19 December 2017</td>
        <td>60604</td>
        <td>Bug Fixes</td>
    </tr>
</table>
"""


def test_extract_rows_from_headerless_table():
    soup = BeautifulSoup(HEADERLESS_TABLE_HTML, "html.parser")
    table = soup.find("table")
    assert table is not None
    rows = extract_rows_from_table(table)

    assert len(rows) == 2
    assert rows[0].patch_id == "4.1.3"
    assert rows[0].build == "61021"
    assert rows[0].release_date_na == date(2018, 1, 9)


def test_extract_rows_with_bu_suffix():
    html = """
    <table class="wikitable">
        <tr>
            <td>Patch 4.0.2 BU</td>
            <td>28 November 2017</td>
            <td>59877</td>
            <td>Balance Changes</td>
        </tr>
    </table>
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    assert table is not None
    rows = extract_rows_from_table(table)

    assert len(rows) == 1
    assert rows[0].patch_id == "4.0.2 BU"


def test_extract_rows_filters_invalid_versions():
    html = """
    <table class="wikitable">
        <tr>
            <td>Patch 4.1.3</td>
            <td>9 January 2018</td>
            <td>61021</td>
            <td>Bug Fixes</td>
        </tr>
        <tr>
            <td>Some header text</td>
            <td>Not a date</td>
            <td>N/A</td>
            <td>Description</td>
        </tr>
    </table>
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    assert table is not None
    rows = extract_rows_from_table(table)

    assert len(rows) == 1
    assert rows[0].patch_id == "4.1.3"


def test_extract_rows_handles_missing_columns():
    html = """
    <table class="wikitable">
        <tr>
            <td>Patch 4.1.3</td>
            <td>9 January 2018</td>
        </tr>
    </table>
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    assert table is not None
    rows = extract_rows_from_table(table)

    assert len(rows) == 1
    assert rows[0].patch_id == "4.1.3"
    assert rows[0].build is None
    assert rows[0].release_date_na == date(2018, 1, 9)


# =============================================================================
# Test: extract_all_rows (multiple tables)
# =============================================================================

MULTI_TABLE_HTML = """
<div>
    <table class="wikitable">
        <tr>
            <td>Patch 4.1.3</td>
            <td>9 January 2018</td>
            <td>61021</td>
            <td>Bug Fixes</td>
        </tr>
    </table>
    <table class="wikitable">
        <tr>
            <td>Patch 3.19.1</td>
            <td>12 October 2017</td>
            <td>58600</td>
            <td>General</td>
        </tr>
    </table>
</div>
"""


def test_extract_all_rows_combines_tables():
    soup = BeautifulSoup(MULTI_TABLE_HTML, "html.parser")
    rows = extract_all_rows(soup)

    assert len(rows) == 2
    versions = [r.patch_id for r in rows]
    assert "4.1.3" in versions
    assert "3.19.1" in versions


def test_extract_all_rows_empty_when_no_tables():
    soup = BeautifulSoup("<div>No tables</div>", "html.parser")
    rows = extract_all_rows(soup)
    assert len(rows) == 0


# =============================================================================
# Test: write_csv
# =============================================================================

def test_write_csv_creates_file():
    rows = [
        PatchRow(patch_id="5.0.11", build="12345", release_date_na=date(2022, 1, 15)),
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        path = f.name

    try:
        write_csv(rows, path)
        assert os.path.exists(path)

        with open(path, "r") as f:
            reader = csv.reader(f)
            header = next(reader)
            assert header == ["patch_id", "build", "release_date_na"]

            row = next(reader)
            assert row == ["5.0.11", "12345", "2022-01-15"]
    finally:
        os.unlink(path)


def test_write_csv_sorts_by_date():
    rows = [
        PatchRow(patch_id="5.0.12", build="12346", release_date_na=date(2022, 1, 20)),
        PatchRow(patch_id="5.0.10", build="12344", release_date_na=date(2022, 1, 5)),
        PatchRow(patch_id="5.0.11", build="12345", release_date_na=date(2022, 1, 15)),
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        path = f.name

    try:
        write_csv(rows, path)

        with open(path, "r") as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            data = list(reader)

        # Should be sorted by date ascending
        assert data[0][0] == "5.0.10"
        assert data[1][0] == "5.0.11"
        assert data[2][0] == "5.0.12"
    finally:
        os.unlink(path)


def test_write_csv_handles_none_values():
    rows = [
        PatchRow(patch_id="5.0.11", build=None, release_date_na=None),
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        path = f.name

    try:
        write_csv(rows, path)

        with open(path, "r") as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            row = next(reader)

        assert row == ["5.0.11", "", ""]
    finally:
        os.unlink(path)


def test_write_csv_handles_bu_suffix():
    rows = [
        PatchRow(patch_id="4.0.2 BU", build="59877", release_date_na=date(2017, 11, 28)),
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        path = f.name

    try:
        write_csv(rows, path)

        with open(path, "r") as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            row = next(reader)

        assert row[0] == "4.0.2 BU"
    finally:
        os.unlink(path)


# =============================================================================
# Integration test with realistic Liquipedia-style HTML
# =============================================================================

REALISTIC_LIQUIPEDIA_HTML = """
<div class="mw-parser-output">
    <table class="wikitable">
        <tr>
            <th>Notes</th>
            <th>Release date (NA)</th>
            <th>Build</th>
            <th>Highlights</th>
        </tr>
        <tr>
            <td><a href="/starcraft2/Patch_5.0.15">Patch 5.0.15</a></td>
            <td>30 September 2025</td>
            <td>95248</td>
            <td>Bug Fixes</td>
        </tr>
        <tr>
            <td><a href="/starcraft2/Patch_5.0.14">Patch 5.0.14</a></td>
            <td>25 November 2024</td>
            <td>93272</td>
            <td>Bug Fixes</td>
        </tr>
    </table>
    <table class="wikitable">
        <tr>
            <th>Notes</th>
            <th>Release date (NA)</th>
            <th>Build</th>
            <th>Highlights</th>
        </tr>
        <tr>
            <td><a href="/starcraft2/Patch_4.0.2_BU">Patch 4.0.2 BU</a></td>
            <td>28 November 2017</td>
            <td>59877</td>
            <td>Balance Changes</td>
        </tr>
        <tr>
            <td><a href="/starcraft2/Patch_4.0.2">Patch 4.0.2</a></td>
            <td>21 November 2017</td>
            <td>59877</td>
            <td>Bug Fixes</td>
        </tr>
    </table>
</div>
"""


def test_integration_liquipedia_structure():
    soup = BeautifulSoup(REALISTIC_LIQUIPEDIA_HTML, "html.parser")
    rows = extract_all_rows(soup)

    assert len(rows) == 4

    # Check specific rows
    row_515 = next(r for r in rows if r.patch_id == "5.0.15")
    assert row_515.build == "95248"
    assert row_515.release_date_na == date(2025, 9, 30)

    row_bu = next(r for r in rows if r.patch_id == "4.0.2 BU")
    assert row_bu.build == "59877"
    assert row_bu.release_date_na == date(2017, 11, 28)


def test_integration_full_pipeline():
    soup = BeautifulSoup(REALISTIC_LIQUIPEDIA_HTML, "html.parser")
    rows = extract_all_rows(soup)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        path = f.name

    try:
        write_csv(rows, path)

        with open(path, "r") as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            data = list(reader)

        # Should have 4 rows, sorted by date
        assert len(data) == 4
        # Earliest date first (21 November 2017)
        assert data[0][0] == "4.0.2"
    finally:
        os.unlink(path)
