"""Published district totals used as external checks, read from the SEC PDFs.

Both tables are read from the text layer with pdftotext, which shares no code
with the pdfplumber table parser used for the winner lists, and are checked
against their own printed totals before use.
"""

import re
import subprocess

from local_elections_odisha.parse.common import RAW, fold

SEC = RAW / "sec/files"
RESERVATION_2022 = next(
    (SEC / "table_056").glob("*RESERVATION-OF-WARD-MEMBER-SARPANCH*.pdf")
)
INFO_2017 = next((SEC / "table_068").glob("*INFORMATION-ON-G.E-TO-PRIS-2017.pdf"))
# SEC spellings that differ from the headings of the winner lists.
ALIAS = {
    "baragarh": "bargarh",
    "khurda": "khordha",
    "sundergarh": "sundargarh",
}
CATEGORIES = ["SC", "SCW", "ST", "STW", "RW", "UR"]


def district_key(name):
    k = fold(name)
    return ALIAS.get(k, k)


def text(pdf):
    out = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout


def _rows(block, ncols):
    rows = {}
    total = None
    for line in block.splitlines():
        m = re.match(r"^\s*(\d+)\s+([A-Z][A-Z ]*?)\s{2,}([\d\s]+)$", line)
        t = re.match(r"^\s*(?:TOTAL)?\s+([\d\s]+)$", line)
        if m:
            nums = [int(x) for x in m.group(3).split()]
            if len(nums) == ncols:
                rows[district_key(m.group(2).replace(" ", ""))] = nums
        elif t and len(t.group(1).split()) == ncols:
            total = [int(x) for x in t.group(1).split()]
    return rows, total


def sarpanch_reservation_2022():
    """{district: {category: seats, 'TOTAL': seats}} from the SEC table of
    8 Jan 2022 ("RESERVATION OF SARPANCH (DISTRICT WISE)-2022")."""
    t = text(RESERVATION_2022)
    start = t.index("RESERVATION OF SARPANCH")
    end = t.index("RESERVATION OF PANCHAYAT SAMITI", start)
    rows, total = _rows(t[start:end], 7)
    if len(rows) != 30 or [sum(c) for c in zip(*rows.values(), strict=True)] != total:
        raise SystemExit("2022 sarpanch reservation table read wrongly")
    return {
        d: dict(zip([*CATEGORIES, "TOTAL"], v, strict=True)) for d, v in rows.items()
    }


def gram_panchayats_2017():
    """{district: GPs} from the 2017 information book's general table."""
    t = text(INFO_2017)
    # columns: sub-divisions, blocks, ZP, PS and GP constituencies, wards, voters
    rows, total = _rows(t, 7)
    gps = {d: v[4] for d, v in rows.items()}
    if len(gps) != 30 or sum(gps.values()) != total[4]:
        raise SystemExit("2017 information book read wrongly")
    return gps
