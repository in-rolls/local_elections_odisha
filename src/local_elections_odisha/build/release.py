"""Verify the published files, run the checks, and write data/MANIFEST.json.

Every check states what it appeals to. An `external` check compares the data
with a figure published elsewhere and can catch a misread; an `internal` check
only shows the file agrees with itself. Each records `pass`, `warn`, `fail` or
`not_run` with the reason. `verify` exits non-zero on a raw file whose sha256
differs from data/raw/fetch_log.csv, on a published file whose sha256 differs
from MANIFEST.json, on a `fail` of a check marked `blocking`, or when a check's
status differs from the one recorded in MANIFEST.json.

Commands:
  verify   recompute hashes, run checks, compare with data/MANIFEST.json
  write    rebuild data/MANIFEST.json and the checks block in README.md
"""

import argparse
import csv
import hashlib
import json
import re
import sys

import pandas as pd

from local_elections_odisha.build import reference as ref
from local_elections_odisha.parse.common import DATA, ROOT

MANIFEST = DATA / "MANIFEST.json"
README = ROOT / "README.md"
FETCH_LOG = DATA / "raw/fetch_log.csv"
HAND_CHECK = DATA / "checks/hand_check_2022.csv"
OUTPUTS = [
    "2017/sarpanch_winners.parquet",
    "2022/sarpanch_winners.parquet",
]
KEY = ["district", "block", "gram_panchayat"]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def result(name, appeals_to, status, detail, blocking=False, **numbers):
    return {
        "check": name,
        "appeals_to": appeals_to,
        "status": status,
        "blocking": blocking,
        "detail": detail,
        **numbers,
    }


def counts_vs(df, reference):
    got = df.groupby(df["district"].map(ref.district_key)).size()
    rows = [
        {"district": d, "reference": n, "rows": int(got.get(d, 0))}
        for d, n in sorted(reference.items())
    ]
    table = pd.DataFrame(rows)
    table["diff"] = table["rows"] - table["reference"]
    return table, sorted(set(got.index) - set(reference))


def checks_2022():
    df = pd.read_parquet(DATA / "2022/sarpanch_winners.parquet")
    seats = ref.sarpanch_reservation_2022()
    table, unknown = counts_vs(df, {d: v["TOTAL"] for d, v in seats.items()})
    off = table[table["diff"] != 0]
    out = [
        result(
            "2022_district_counts_vs_sec",
            "external",
            "pass" if off.empty and not unknown else "fail",
            f"Elected-sarpanch rows per district against the SEC's district-wise "
            f"sarpanch reservation table of 8 Jan 2022 (read with pdftotext). "
            f"{len(df):,} rows against {table['reference'].sum():,} seats; "
            f"{len(off)} district(s) differ; unmatched names {unknown}.",
            blocking=True,
            differing=off.to_dict("records"),
        )
    ]
    dup = df[df.duplicated(KEY, keep=False)]
    out.append(
        result(
            "2022_key_unique",
            "internal",
            "pass" if dup.empty else "warn",
            f"{dup[KEY].drop_duplicates().shape[0]} (district, block, GP) keys "
            f"appear more than once ({len(dup)} rows), kept as printed.",
            duplicate_rows=dup[[*KEY, "winner", "source_page"]].to_dict("records"),
        )
    )
    women = sum(v["SCW"] + v["STW"] + v["RW"] for v in seats.values())
    total = sum(v["TOTAL"] for v in seats.values())
    bc = 0  # the 2022 table has no backward-class column
    out.append(
        result(
            "2022_sec_table_women_share",
            "external",
            "pass" if women / total >= 0.5 else "fail",
            f"In the SEC district table, women's seats (SCW + STW + RW) are "
            f"{women:,} of {total:,} ({women / total:.2%}); the Odisha Gram "
            f"Panchayat Act reserves at least half for women. Backward-class "
            f"seats: {bc} (no BC column; the 2021 High Court order). This checks "
            f"the reference table, not a per-GP file.",
            share=round(women / total, 4),
        )
    )
    return out


def checks_2017():
    df = pd.read_parquet(DATA / "2017/sarpanch_winners.parquet")
    table, unknown = counts_vs(df, ref.gram_panchayats_2017())
    off = table[table["diff"] != 0]
    return [
        result(
            "2017_district_counts_vs_sec",
            "external",
            "pass" if off.empty and not unknown else "warn",
            f"Elected-sarpanch rows per district against GPs in the 2017 "
            f"information book: {len(df):,} rows against "
            f"{table['reference'].sum():,} GPs; {len(off)} district(s) differ. "
            f"Sambalpur's link on the SEC site serves the Subarnapur file, and "
            f"Malkangiri's file omits its seventh block; both are source gaps.",
            differing=off.to_dict("records"),
        )
    ]


def hand_check():
    if not HAND_CHECK.exists():
        return result(
            "2022_hand_check",
            "external",
            "not_run",
            "No hand check recorded yet (data/checks/hand_check_2022.csv).",
        )
    rows = list(csv.DictReader(HAND_CHECK.open(encoding="utf-8")))
    done = [r for r in rows if r["matches_pdf"] in ("yes", "no")]
    bad = [r for r in done if r["matches_pdf"] == "no"]
    if len(done) < len(rows):
        status = "not_run"
    else:
        status = "pass" if not bad else "fail"
    return result(
        "2022_hand_check",
        "external",
        status,
        f"{len(done)} of {len(rows)} sampled rows compared by eye with the "
        f"PDF page; {len(bad)} disagree.",
    )


def run_checks():
    return [*checks_2022(), *checks_2017(), hand_check()]


def outputs():
    import pyarrow.parquet as pq

    return [
        {
            "file": rel,
            "sha256": sha256(DATA / rel),
            "rows": pq.read_metadata(DATA / rel).num_rows,
            "schema": [
                {"name": f.name, "type": str(f.type)}
                for f in pq.read_schema(DATA / rel)
            ],
        }
        for rel in OUTPUTS
    ]


def raw_problems():
    with FETCH_LOG.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    bad = []
    for row in rows:
        # a duplicate was deleted on fetch; its bytes are the kept copy's
        path = ROOT / (row.get("duplicate_of") or row["path"])
        if not path.exists():
            bad.append(f"raw file missing: {path.relative_to(ROOT)}")
        elif sha256(path) != row["sha256"]:
            bad.append(f"raw file changed since fetch: {row['path']}")
    logged = {row["path"] for row in rows if not row.get("duplicate_of")}
    for path in sorted((DATA / "raw").rglob("*")):
        rel = str(path.relative_to(ROOT))
        if path.is_file() and path != FETCH_LOG and rel not in logged:
            bad.append(f"raw file not in fetch log: {rel}")
    return bad, len(rows)


def show(checks):
    for c in checks:
        print(f"  {c['status']:8} {c['check']}")


def verify():
    problems, n = raw_problems()
    manifest = json.loads(MANIFEST.read_text())
    for entry in manifest["outputs"]:
        if sha256(DATA / entry["file"]) != entry["sha256"]:
            problems.append(f"output changed since MANIFEST.json: {entry['file']}")
    checks = run_checks()
    show(checks)
    recorded = {c["check"]: c["status"] for c in manifest["checks"]}
    stale = [c["check"] for c in checks if recorded.get(c["check"]) != c["status"]]
    if stale:
        problems.append(f"check status differs from MANIFEST.json: {stale}")
    blocking = [c["check"] for c in checks if c["blocking"] and c["status"] == "fail"]
    if blocking:
        problems.append(f"blocking checks failed: {blocking}")
    print(f"  {n} raw files checked against the fetch log")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        raise SystemExit(1)


def write():
    problems, _ = raw_problems()
    if problems:
        raise SystemExit("\n".join(problems))
    checks = run_checks()
    MANIFEST.write_text(
        json.dumps(
            {"format_version": 1, "outputs": outputs(), "checks": checks},
            indent=1,
            ensure_ascii=False,
        )
        + "\n"
    )
    lines = ["<!-- checks:start -->", "", "| Check | Appeals to | Status | Result |"]
    lines.append("| --- | --- | --- | --- |")
    for c in checks:
        detail = c["detail"].replace("|", "/")
        lines.append(
            f"| `{c['check']}` | {c['appeals_to']} | {c['status']} | {detail} |"
        )
    lines.extend(["", "<!-- checks:end -->"])
    text = README.read_text()
    pattern = r"<!-- checks:start -->.*?<!-- checks:end -->"
    README.write_text(re.sub(pattern, lambda _: "\n".join(lines), text, flags=re.S))
    show(checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["verify", "write"])
    args = parser.parse_args()
    verify() if args.command == "verify" else write()


if __name__ == "__main__":
    main()
