"""Collect the Odisha State Election Commission's PRI documents.

sec.odisha.gov.in (rebuilt in 2026) renders each document list in the browser
from `/CMS/GetCMSTableData?TableId=N`, a JSON array whose `tableData` holds
columns and rows; file cells are site paths under /uploads/cmsfiles/. Read
2026-10-18. Table ids 1-150 were probed then; TABLES below are the ones that
answered with rows.

This saves the landing pages and every table as returned, then downloads the
files about sarpanches, the PRI information books and two reservation
documents (`wanted`). Nothing is parsed here.

Not collected: the "Report Of Last Three Elections" reservation search
(/Landing/ReservationList). Its data endpoint is reached only after a mobile
OTP check in the page; see README.

Run: python -m local_elections_odisha.collect.sec
"""

import json
import logging
import re
from urllib.parse import quote

from local_elections_odisha.collect.fetch import ROOT, fetch, session, setup_logging

BASE = "https://sec.odisha.gov.in"
SOURCE = "sec.odisha.gov.in"
OUT = "data/raw/sec"
TABLES = [10, 11, 13, 14, 15, 17, 18, 20, 27, 28, 29, 30, 33, 34, 35, 36, 37]
TABLES += [39, 40, 42, 43, 45, 46, 48, 56, 57, 58, 59, 60, 61, 64, 65, 66, 67]
TABLES += [68, 69, 70, 71, 75, 76, 77, 78, 79, 81, 82, 83]
PAGES = [
    "Index",
    "ReservationList",
    "ElectedSarpanchPSMember",
    "ElectedSarpanchPSMember2017",
    "GEtoPRIs2017",
    "GEtoPRIs2022",
    "PRIsByElectionAfter2017",
    "PRIsByElectionAfter2022",
    "PRIAtAGlance",
    "LandingArchive",
    "NotificationLettersPRI",
    "PanchayatiRajInstitutionCircular",
    "LandingpImportantJudgements",
]
# Files kept, by table and row title. Everything else on the site (ward,
# samiti, Zilla Parishad and urban-body files, naib-sarpanch and by-election
# notices, blank forms) is out of scope. Several tables repeat a document under
# a different upload id; one copy is kept: information books 1997-2012 from
# table 81 (not 68 or 76), sarpanch by-election results 2017-19 from table 59
# (table 61's 2017 sarpanch link is its P.S member file).
KEEP = {
    # 2022 sarpanch notification; fresh polls where a reserved seat had no taker
    10: r"Ward Member & Sarpanch for General Election"
    r"|Sarapanch/Ward Member due to de-res",
    13: r"Access to Reservation Information",  # 2026 circular, see README
    27: r"FORM-15",  # the blank sarpanch reservation statement
    56: r"INFORMATION BOOK|Reservation of Ward Member, Sarpanch",
    57: r"Elected Sarpanch",  # 2022, all districts
    58: r"ELECTED SARPANCH",  # by-elections 2022-25
    59: r"Elected Sarpanch",  # by-elections 2017-19
    60: r".",  # 2017 elected sarpanches, one row per district
    68: r"PRIs-2017",
    81: r".",
    82: r"34206",  # High Court order on backward-class reservation, 2021
}
SKIP_COLUMN = re.compile(r"P\.S Member", re.I)

log = logging.getLogger("sec")


def rows(table_id):
    raw = json.loads((ROOT / f"{OUT}/cms/table_{table_id:03d}.json").read_text())
    if not raw:
        return []
    return json.loads(raw[0]["tableData"])["rows"]


def wanted(table_id):
    """(site path, title) for each file to keep from a saved table."""
    out = []
    for row in rows(table_id):
        title = " ".join(str(v) for k, v in row.items() if "Download" not in k)
        if table_id not in KEEP or not re.search(KEEP[table_id], title, re.I):
            continue
        for col, val in row.items():
            if SKIP_COLUMN.search(col) or not isinstance(val, str):
                continue
            if val.startswith("/uploads/") and val.lower().endswith(".pdf"):
                out.append((val, title))
    return out


def main():
    setup_logging("collect_sec")
    s = session()
    for page in PAGES:
        fetch(f"{BASE}/Landing/{page}", f"{OUT}/pages/{page}.html", SOURCE, s)
    for t in TABLES:
        url = f"{BASE}/CMS/GetCMSTableData?TableId={t}"
        fetch(url, f"{OUT}/cms/table_{t:03d}.json", SOURCE, s)
    seen = set()
    for t in TABLES:
        for path, title in wanted(t):
            if path in seen:
                continue
            seen.add(path)
            name = path.rsplit("/", 1)[-1].replace(" ", "_")
            rel = f"{OUT}/files/table_{t:03d}/{name}"
            log.info("table %d: %s", t, title[:80])
            fetch(BASE + quote(path), rel, SOURCE, s, timeout=600)


if __name__ == "__main__":
    main()
