"""Collect sarpanch reservation statements from the district collectorate sites.

The collector of each district publishes the final statement of sarpanch seat
reservation for every gram panchayat (Form 15 under rule 3-A of the Odisha
Gram Panchayat Election Rules, 1965). The SEC site does not carry these. The
district sites (NIC S3WaaS, Drupal) have a keyword search at
/en/search/node?keys=...; each hit is a notice page that links its PDF under
/sites/default/files/.

For every district this saves the search pages for "reservation",
"sarpanch" and "sarapanch" (both spellings occur), keeps hits whose title
mentions both reservation and sarpanch, saves those notice pages and downloads
their PDFs. Draft and
final statements are both kept; the parser tells them apart.

Run: python -m local_elections_odisha.collect.districts
"""

import html
import logging
import re
from urllib.parse import urljoin, urlparse

import requests

from local_elections_odisha.collect.fetch import fetch, session, setup_logging

OUT = "data/raw/districts"
DISTRICTS = [
    "angul",
    "balangir",
    "balasore",
    "bargarh",
    "bhadrak",
    "boudh",
    "cuttack",
    "deogarh",
    "dhenkanal",
    "gajapati",
    "ganjam",
    "jagatsinghpur",
    "jajpur",
    "jharsuguda",
    "kalahandi",
    "kandhamal",
    "kendrapada",
    "kendujhar",
    "khordha",
    "koraput",
    "malkangiri",
    "mayurbhanj",
    "nabarangpur",
    "nayagarh",
    "nuapada",
    "puri",
    "rayagada",
    "sambalpur",
    "subarnapur",
    "sundargarh",
]
# Drupal matches whole words, so "sarpanch" misses "Sarpanches".
QUERIES = ["reservation", "sarpanch", "sarapanch"]
MAX_PAGES = 10
HIT = re.compile(r'<h3[^>]*>\s*<a href="([^"]+)"[^>]*>(.*?)</a>', re.S)
# The notice's own attachment is a link labelled "Download (size)" or "View
# Document (size)", or one wrapped in <span class="file ...">; the menus on
# every page link unrelated PDFs.
PDF = re.compile(
    r'href="([^"]+\.pdf)"[^>]*>\s*(?:Download|View Document)\b'
    r'|<span class="file[^"]*">\s*<a href="([^"]+\.pdf)"',
    re.I,
)
WANT = re.compile(r"reserv.*sara?panch|sara?panch.*reserv", re.I)
# Sambalpur's ward-member drafts (Form 13) name the sarpanch form in passing.
SKIP = re.compile(r"Form no\. 13 \(for Ward Members\)", re.I)

log = logging.getLogger("districts")


def text(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def https(url, host):
    p = urlparse(urljoin(f"https://{host}/", url))
    return p._replace(scheme="https", netloc=host).geturl()


def slug(url):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", urlparse(url).path.strip("/"))[:150]


def hits(district, s):
    host = f"{district}.odisha.gov.in"
    found = {}
    for q in QUERIES:
        for page in range(MAX_PAGES):
            url = f"https://{host}/en/search/node?keys={q}&page={page}"
            rel = f"{OUT}/{district}/search/{q}_{page:02d}.html"
            body = fetch(url, rel, host, s).read_text(
                encoding="utf-8", errors="replace"
            )
            got = HIT.findall(body)
            for href, title in got:
                found.setdefault(https(href, host), text(title))
            if not got or "pager__item--next" not in body:
                break
    return found


def collect(district, s):
    host = f"{district}.odisha.gov.in"
    for url, title in hits(district, s).items():
        if not WANT.search(title) or SKIP.search(title):
            continue
        log.info("%s: %s", district, title[:100])
        page = fetch(url, f"{OUT}/{district}/notices/{slug(url)}.html", host, s)
        body = page.read_text(encoding="utf-8", errors="replace")
        for href in dict.fromkeys(a or b for a, b in PDF.findall(body)):
            pdf = https(href, host)
            name = urlparse(pdf).path.rsplit("/", 1)[-1]
            fetch(pdf, f"{OUT}/{district}/files/{name}", host, s, timeout=600)


def main():
    setup_logging("collect_districts")
    s = session()
    for district in DISTRICTS:
        try:
            collect(district, s)
        except (requests.RequestException, RuntimeError) as exc:
            log.error("%s: %s", district, exc)


if __name__ == "__main__":
    main()
