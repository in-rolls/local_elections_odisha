"""Polite, resumable fetching with a receipt for every saved response.

Every response that is kept is written once under data/raw/ and logged in
data/raw/fetch_log.csv with its URL, sha256, size, HTTP status and UTC fetch
time. A path already in the log is never fetched again, so an interrupted run
resumes where it stopped and a re-run cannot silently replace a source.
"""

import csv
import hashlib
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw"
LOG = RAW / "fetch_log.csv"
# The first six are local_elections docs/layout.md's required columns.
FIELDS = [
    "path",
    "url",
    "sha256",
    "bytes",
    "fetched_at_utc",
    "method",
    "copied_from",
    "source",
    "status",
    "duplicate_of",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (research data collection; in-rolls)"}
# sec.odisha.gov.in refuses connections from outside India; route through a
# SOCKS5 tunnel to an Indian host. socks5h resolves names on the far side.
PROXY = os.environ.get("ODISHA_PROXY", "socks5h://localhost:1080")

log = logging.getLogger("fetch")


def session():
    s = requests.Session()
    s.headers.update(HEADERS)
    if PROXY:
        s.proxies = {"http": PROXY, "https": PROXY}
    return s


def setup_logging(name):
    (ROOT / "logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(ROOT / "logs" / f"{name}.log"),
            logging.StreamHandler(),
        ],
    )


def contained(rel):
    """ROOT/rel, refused unless it resolves inside data/raw/. Local names are
    built from server-supplied paths, so a crafted one could climb out."""
    path = (ROOT / rel).resolve()
    if not path.is_relative_to(RAW.resolve()):
        raise ValueError(f"refusing to write outside data/raw/: {rel!r}")
    return path


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def logged():
    if not LOG.exists():
        return {}
    with LOG.open(encoding="utf-8") as fh:
        return {row["path"]: row for row in csv.DictReader(fh)}


def record(rel, url, source, status):
    """Log a saved file. A file byte-identical to one already logged is
    deleted and logged with `duplicate_of` naming the kept copy: district
    sites often attach one PDF to several notices under different names."""
    path = contained(rel)
    digest = sha256(path)
    kept = next(
        (
            row["path"]
            for row in logged().values()
            if row["sha256"] == digest and not row.get("duplicate_of")
        ),
        "",
    )
    size = path.stat().st_size
    if kept and kept != rel:
        path.unlink()
    new = not LOG.exists()
    with LOG.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        if new:
            writer.writeheader()
        writer.writerow(
            {
                "path": rel,
                "url": url,
                "source": source,
                "sha256": digest,
                "bytes": size,
                "status": status,
                "fetched_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "method": "live",
                "copied_from": "",
                "duplicate_of": kept if kept != rel else "",
            }
        )
    return contained(kept or rel)


def save(content, rel, url, source, status):
    """Write a response body obtained some other way (e.g. a POST) and log it."""
    path = contained(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return record(rel, url, source, status)


def fetch(url, rel, source, sess=None, delay=2.0, retries=5, timeout=120):
    """Save url to ROOT/rel unless already logged; return the local path.

    Connection errors and 429/5xx back off and retry; the tunnel is shared, so
    every request, kept or not, is followed by at least `delay` seconds.
    """
    path = contained(rel)
    row = logged().get(rel)
    if row and row.get("duplicate_of"):
        return contained(row["duplicate_of"])
    if row and path.exists():
        return path
    sess = sess or session()
    for attempt in range(1, retries + 1):
        try:
            resp = sess.get(url, timeout=timeout)
        except requests.RequestException as exc:
            wait = min(300, delay * 5 * 2**attempt)
            log.warning("%s: %s; retry %d in %.0fs", url, exc, attempt, wait)
            if attempt == retries:
                raise
            time.sleep(wait)
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = min(300, delay * 5 * 2**attempt)
            log.warning(
                "%s: HTTP %d; retry %d in %.0fs", url, resp.status_code, attempt, wait
            )
            time.sleep(wait)
            continue
        resp.raise_for_status()
        kept = save(resp.content, rel, url, source, resp.status_code)
        log.info("saved %s (%d bytes)", rel, len(resp.content))
        time.sleep(delay)
        return kept
    raise RuntimeError(f"gave up on {url} after {retries} attempts")
