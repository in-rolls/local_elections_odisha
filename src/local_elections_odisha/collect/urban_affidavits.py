"""Fetch exact-name, same-ward Bhubaneswar winner affidavit candidates."""

import argparse
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import pdfplumber
import pyarrow.parquet as pq
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from local_elections_odisha.collect.fetch import ROOT
from local_elections_odisha.collect.fetch import record as register_source

RELEASE = ROOT / "data/release/urban"
OUT = ROOT / "data/raw/sec/urban/affidavits"


def normalize(value):
    return re.sub(r"[^a-z]", "", value.casefold())


def frame():
    winners = {
        r["ward_no"]: r
        for r in pq.read_table(RELEASE / "winners.parquet").to_pylist()
        if r["year"] == 2022 and r["body"] == "Bhubaneswar Municipal Corporation"
    }
    output = []
    for r in pq.read_table(RELEASE / "affidavit_documents.parquet").to_pylist():
        if r["office"] != "ward_councilor":
            continue
        name = re.sub(r"\s*\(?\d+\)?$", "", r["candidate_label"])
        winner = winners[r["ward_no"]]
        if normalize(name) == normalize(winner["winner"]):
            output.append(
                {
                    **r,
                    "winner": winner["winner"],
                    "link_basis": "same_ward_exact_normalized_name",
                    "filing_status": "not_checked_for_supersession",
                }
            )
    return output


def fetch_one(record, out):
    receipt = {
        "document_serial": record["document_serial"],
        "ward_no": record["ward_no"],
        "url": record["document_url"],
        "fetched_at_utc": datetime.now(UTC).isoformat(),
    }
    with requests.Session() as session:
        session.headers.update(
            {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bmc.gov.in/"}
        )
        retry = Retry(
            total=2, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504]
        )
        session.mount("https://", HTTPAdapter(max_retries=retry))
        try:
            response = session.get(record["document_url"], timeout=(20, 90))
            receipt.update(
                http_status=response.status_code,
                response_url=response.url,
                content_type=response.headers.get("Content-Type"),
                bytes=len(response.content),
            )
            response.raise_for_status()
            if not response.content.startswith(b"%PDF"):
                raise ValueError("Response is not a PDF")
            path = out / f"document_{record['document_serial']:03d}.pdf"
            temp = path.with_suffix(".part")
            temp.write_bytes(response.content)
            with pdfplumber.open(temp) as pdf:
                pages = len(pdf.pages)
                if not pages:
                    raise ValueError("PDF has no pages")
            temp.replace(path)
            receipt.update(
                ok=True,
                path=str(path.relative_to(ROOT)),
                sha256=hashlib.sha256(response.content).hexdigest(),
                pdf_pages=pages,
            )
        except (requests.RequestException, ValueError) as exc:
            receipt.update(ok=False, error=f"{type(exc).__name__}: {exc}")
    return receipt


def collect(out=OUT, workers=2):
    out.mkdir(parents=True, exist_ok=True)
    plan = frame()
    reference = ROOT / "data/search_log/urban/affidavits"
    reference.mkdir(parents=True, exist_ok=True)
    ledger = reference / "receipts.jsonl"
    receipts = (
        [json.loads(s) for s in ledger.read_text().splitlines()]
        if ledger.exists()
        else []
    )
    done = {}
    for r in receipts:
        if r.get("ok"):
            path = ROOT / r["path"]
            if (
                path.exists()
                and hashlib.sha256(path.read_bytes()).hexdigest() == r["sha256"]
            ):
                done[r["document_serial"]] = r
    pending = [r for r in plan if r["document_serial"] not in done]
    print(
        json.dumps(
            {"planned": len(plan), "already_saved": len(done), "pending": len(pending)}
        ),
        flush=True,
    )
    with ThreadPoolExecutor(max_workers=workers) as pool, ledger.open("a") as handle:
        for future in as_completed([pool.submit(fetch_one, r, out) for r in pending]):
            r = future.result()
            if r.get("ok"):
                requested = r["path"]
                kept = register_source(
                    requested, r["url"], "cms.bhubaneswarone.in", r["http_status"]
                )
                r["path"] = str(kept.relative_to(ROOT))
                if requested != r["path"]:
                    r.update(requested_path=requested, duplicate_of=r["path"])
            handle.write(json.dumps(r, ensure_ascii=False) + "\n")
            handle.flush()
            print(
                json.dumps(
                    {k: r.get(k) for k in ["document_serial", "ok", "bytes", "error"]}
                ),
                flush=True,
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.workers <= 2:
        parser.error("Use one or two workers")
    collect(workers=args.workers)


if __name__ == "__main__":
    main()
