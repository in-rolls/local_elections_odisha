"""Build urban winner records and the official affidavit index from retained sources."""

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import pdfplumber
import pyarrow as pa
import pyarrow.parquet as pq
from bs4 import BeautifulSoup

from local_elections_odisha.build import urban_contract as contract
from local_elections_odisha.collect.fetch import ROOT

RAW = ROOT / "data/raw/sec/urban"
MANUAL = ROOT / "data/manual/urban"
SEARCH_LOG = ROOT / "data/search_log/urban"
RELEASE = ROOT / "data/release/urban"
RESERVATIONS = {
    "Unreserved": ("NONE", 0),
    "Reserved For Woman": ("NONE", 1),
    "Scheduled Caste": ("SC", 0),
    "Scheduled Caste Woman": ("SC", 1),
    "Scheduled Tribe": ("ST", 0),
    "Scheduled Tribe Woman": ("ST", 1),
}
SCHEMA = contract.schema("winners")
INDEX_SCHEMA = contract.schema("affidavit_documents")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_sources(manual=MANUAL, search_log=SEARCH_LOG):
    receipts = json.loads((search_log / "acquisition_receipts.json").read_text())
    for r in receipts:
        path = ROOT / r["path"]
        if digest(path) != r["sha256"] or path.stat().st_size != r["bytes"]:
            raise ValueError(f"Source checksum mismatch: {path}")
        if path.suffix == ".pdf" and not path.read_bytes().startswith(b"%PDF"):
            raise ValueError(f"Not a PDF: {path}")
    r = json.loads((manual / "transcription_receipt.json").read_text())
    path = manual / "corporators_2014_transcription.csv"
    if digest(path) != r["sha256"]:
        raise ValueError("Historical transcription checksum mismatch")
    if digest(ROOT / r["source_file"]) != r["source_sha256"]:
        raise ValueError("Historical PDF checksum mismatch")
    return r


def historical(reference, receipt):
    rows = []
    with (reference / "corporators_2014_transcription.csv").open() as f:
        for r in csv.DictReader(f):
            rows.append(
                {
                    "year": int(r["year"]),
                    "body": r["city"] + " Municipal Corporation",
                    "ward_no": r["ward_no"],
                    "winner": r["winner_name_raw"],
                    "winner_raw": r["winner_name_raw"],
                    "winner_basis": "published",
                    "winner_woman_basis": "not_reported",
                    "reserved_basis": "not_reported",
                    "source_path": receipt["source_file"],
                    "source_sha256": receipt["source_sha256"],
                    "source_page": int(r["source_pdf_page"]),
                    "source_column": int(r["source_column"]),
                    "source_row": int(r["source_row"]),
                    "extraction_method": "visual_transcription",
                    "raw_record_json": json.dumps(r, ensure_ascii=False),
                }
            )
    return rows


def current(path):
    rows = []
    source_hash = digest(path)
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            tables = page.extract_tables()
            if not tables or any(t[0] != ["Party-wise tally"] for t in tables[1:]):
                raise ValueError(f"Unexpected tables on page {page_no}")
            for row_no, cells in enumerate(tables[0], 1):
                if not cells[0] or not cells[0].isdigit():
                    continue
                if len(cells) != 7 or any(c is None for c in cells):
                    raise ValueError(f"Malformed winner row: {cells}")
                c = [" ".join(v.split()) for v in cells]
                body = c[2]
                match = re.fullmatch(r"WARD (\d+)", c[3])
                if body not in contract.BODY_COUNTS or match is None:
                    raise ValueError(f"Unexpected ward/body: {c}")
                if c[4] not in RESERVATIONS or not c[5] or not c[6]:
                    raise ValueError(f"Unrecognized winner/reservation: {c}")
                reserved_caste, reserved_woman = RESERVATIONS[c[4]]
                rows.append(
                    {
                        "year": 2022,
                        "body": body,
                        "ward_no": match[1],
                        "winner": c[5],
                        "winner_raw": cells[5],
                        "winner_basis": "published",
                        "winner_woman_basis": "not_reported",
                        "reserved_basis": "source_cell",
                        "winner_party": c[6],
                        "winner_party_raw": cells[6],
                        "reserved_raw": cells[4],
                        "reserved_caste": reserved_caste,
                        "reserved_woman": reserved_woman,
                        "source_path": str(path.relative_to(ROOT)),
                        "source_sha256": source_hash,
                        "source_page": page_no,
                        "source_row": row_no,
                        "extraction_method": "pdf_table_text",
                        "raw_record_json": json.dumps(cells, ensure_ascii=False),
                    }
                )
    return rows


def affidavit_index(path):
    soup = BeautifulSoup(path.read_bytes(), "html.parser")
    output = []
    for a in soup.select("a[href]"):
        url = a["href"]
        if "Affidavits Submitted By The Candidates For ULB Election 2022/" not in url:
            continue
        label = a.get_text(" ", strip=True)
        match = re.fullmatch(r"(\d+)\s+(Mayor\s*-|W-\s*(\d+))\s*(.+)", label)
        if not match:
            raise ValueError(f"Unexpected affidavit title: {label}")
        output.append(
            {
                "year": 2022,
                "body": "Bhubaneswar Municipal Corporation",
                "document_serial": int(match[1]),
                "title": label,
                "title_raw": a.get_text(),
                "office": "mayor" if match[3] is None else "ward_councilor",
                "ward_no": match[3],
                "candidate_label": match[4],
                "document_url": url,
                "source_path": str(path.relative_to(ROOT)),
                "source_sha256": digest(path),
            }
        )
    if len(output) != 365 or {r["document_serial"] for r in output} != set(
        range(1, 366)
    ):
        raise ValueError("Incomplete affidavit document frame")
    return output


def attach_downloads(documents):
    ledger = SEARCH_LOG / "affidavits/receipts.jsonl"
    receipts = (
        {
            r["document_serial"]: r
            for r in map(json.loads, ledger.read_text().splitlines())
        }
        if ledger.exists()
        else {}
    )
    checked = set()
    for row in documents:
        receipt = receipts.get(row["document_serial"])
        row["download_status"] = "not_attempted"
        if receipt is None:
            continue
        if receipt["url"] != row["document_url"]:
            raise ValueError("Affidavit receipt URL does not match directory")
        row["download_status"] = "saved" if receipt.get("ok") else "failed"
        if receipt.get("ok"):
            path = ROOT / receipt["path"]
            if path not in checked:
                if (
                    digest(path) != receipt["sha256"]
                    or path.stat().st_size != receipt["bytes"]
                ):
                    raise ValueError(f"Affidavit source changed: {path}")
                checked.add(path)
            row.update(
                downloaded_path=receipt["path"],
                downloaded_bytes=receipt["bytes"],
                downloaded_at=datetime.fromisoformat(receipt["fetched_at_utc"]),
                downloaded_sha256=receipt["sha256"],
                pdf_pages=receipt["pdf_pages"],
            )


def tables_from_sources():
    receipt = verify_sources()
    rows = historical(MANUAL, receipt) + current(RAW / "corporators_2022.pdf")
    rows.sort(key=lambda r: (r["year"], r["body"], int(r["ward_no"])))
    documents = affidavit_index(RAW / "bmc_affidavits.html")
    attach_downloads(documents)
    tables = {
        "winners": pa.Table.from_pylist(rows, schema=SCHEMA),
        "affidavit_documents": pa.Table.from_pylist(documents, schema=INDEX_SCHEMA),
    }
    for name, table in tables.items():
        contract.validate_table(table, name)
    return tables


def profile(tables):
    rows = tables["winners"].to_pylist()
    documents = tables["affidavit_documents"].to_pylist()
    return {
        "winner_rows": len(rows),
        "body_year_counts": {
            f"{year}_{body}": count
            for (year, body), count in sorted(
                Counter((r["year"], r["body"]) for r in rows).items()
            )
        },
        "winner_woman_recorded": sum(r["winner_woman"] is not None for r in rows),
        "reserved_woman_recorded": sum(r["reserved_woman"] is not None for r in rows),
        "reserved_woman_2022": dict(
            Counter(r["body"] for r in rows if r["reserved_woman"] == 1)
        ),
        "affidavit_document_links": len(documents),
        "affidavit_offices": dict(Counter(r["office"] for r in documents)),
        "affidavit_ward_coverage": len(
            {r["ward_no"] for r in documents if r["ward_no"]}
        ),
        "affidavit_downloads": dict(Counter(r["download_status"] for r in documents)),
        "affidavit_unique_saved_files": len(
            {r["downloaded_path"] for r in documents if r["download_status"] == "saved"}
        ),
        "validated_geographic_transitions": 0,
    }


def dictionary_rows():
    return [
        {
            "table": name,
            "column": f["name"],
            "type": str(f["arrow"]),
            "nullable": f["nullable"],
            "primary_key": f["name"] in spec["primary_key"],
            "allowed_values": json.dumps(f["values"])
            if f["values"] is not None
            else "",
            "definition": f["description"],
        }
        for name, spec in contract.CONTRACTS.items()
        for f in spec["fields"]
    ]


def dictionary_text():
    definitions = dictionary_rows()
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=list(definitions[0]), lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(definitions)
    return buffer.getvalue()


def source_manifest(tables):
    paths = {
        str(path.relative_to(ROOT))
        for path in [
            SEARCH_LOG / "acquisition_receipts.json",
            MANUAL / "transcription_receipt.json",
            MANUAL / "corporators_2014_transcription.csv",
            SEARCH_LOG / "affidavits/receipts.jsonl",
        ]
    }
    for table in tables.values():
        paths.update(table["source_path"].to_pylist())
    paths.update(
        r["downloaded_path"]
        for r in tables["affidavit_documents"].to_pylist()
        if r["downloaded_path"] is not None
    )
    paths.update(
        r["path"]
        for r in json.loads((SEARCH_LOG / "acquisition_receipts.json").read_text())
    )
    with (ROOT / "data/raw/fetch_log.csv").open() as handle:
        acquisitions = {r["path"]: r for r in csv.DictReader(handle)}
    return {
        "inputs": [
            {
                "path": path,
                "sha256": digest(ROOT / path),
                "bytes": (ROOT / path).stat().st_size,
                "acquisition": acquisitions.get(path),
            }
            for path in sorted(paths)
        ]
    }


def build(release=RELEASE):
    tables = tables_from_sources()
    release.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        path = release / f"{name}.parquet"
        pq.write_table(table, path, compression="zstd")
        if not table.equals(pq.read_table(path)):
            raise ValueError("Parquet round trip changed values")
    for name, value in [
        ("schema.json", contract.metadata()),
        ("profile.json", profile(tables)),
        ("sources.json", source_manifest(tables)),
    ]:
        (release / name).write_text(json.dumps(value, indent=2) + "\n")
    (release / "dictionary.csv").write_text(dictionary_text())
    files = [
        "winners.parquet",
        "affidavit_documents.parquet",
        "schema.json",
        "profile.json",
        "sources.json",
        "dictionary.csv",
    ]
    hashes = {name: digest(release / name) for name in files}
    (release / "checksums.json").write_text(json.dumps(hashes, indent=2) + "\n")
    verify_release(release)
    print(json.dumps(profile(tables), indent=2))


def verify_release(release=None):
    release = RELEASE if release is None else release
    tables = {
        name: pq.read_table(release / f"{name}.parquet") for name in contract.CONTRACTS
    }
    for name, table in tables.items():
        contract.validate_table(table, name)
    expected = contract.metadata()
    if json.loads((release / "schema.json").read_text()) != expected:
        raise ValueError("Urban schema metadata differs from code contract")
    if json.loads((release / "profile.json").read_text()) != profile(tables):
        raise ValueError("Urban profile differs from released tables")
    checksums = json.loads((release / "checksums.json").read_text())
    expected_files = {f"{name}.parquet" for name in contract.CONTRACTS} | {
        "schema.json",
        "profile.json",
        "sources.json",
        "dictionary.csv",
    }
    if set(checksums) != expected_files:
        raise ValueError("Urban checksum manifest does not cover every output")
    if (release / "dictionary.csv").read_text() != dictionary_text():
        raise ValueError("Urban dictionary differs from code contract")
    if json.loads((release / "sources.json").read_text()) != source_manifest(tables):
        raise ValueError("Urban source manifest differs from current input records")
    for name, expected_hash in checksums.items():
        if digest(release / name) != expected_hash:
            raise ValueError(f"Urban output checksum mismatch: {name}")
    inputs = json.loads((release / "sources.json").read_text())["inputs"]
    for r in inputs:
        path = ROOT / r["path"]
        if digest(path) != r["sha256"] or path.stat().st_size != r["bytes"]:
            raise ValueError(f"Urban input changed: {r['path']}")
    return {name: table.num_rows for name, table in tables.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=RELEASE)
    build(parser.parse_args().out)


if __name__ == "__main__":
    main()
