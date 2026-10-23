# Odisha Sarpanch Elections

[![Code license: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)

Odisha's gram panchayat (GP) head (sarpanch) elections of 2017 and 2022: one
row per GP with its elected sarpanch, and every row points back to the PDF
page it was read from. The raw sources are committed under
[data/raw/](data/raw/), each logged with its URL, sha256 and fetch time in
[data/raw/fetch_log.csv](data/raw/fetch_log.csv).

This is a sister repository of
[in-rolls/local_elections](https://github.com/in-rolls/local_elections).

## Status: read this first

| | 2017 | 2022 |
|---|---|---|
| GPs with a winner row | 6,640 of 6,801 (29 of 30 districts) | 6,794 of 6,794 |
| Winner names | Latin script | Latin script |
| Reservation per GP | **no** | **no** (district totals only) |
| Source | SEC, one PDF per district | SEC, one statewide PDF |

**Reservation per GP is not in this repository yet.** The State Election
Commission (SEC) winner lists print no category. Where the reservation exists:

- **District totals for 2022** (SC, SC woman, ST, ST woman, unreserved woman,
  unreserved) are in the SEC table of 8 Jan 2022, used here as a check. It has
  no backward-class (BC) column: the Orissa High Court's order in W.P.(C)
  34206/2021 (in `data/raw/sec/files/table_082/`) removed BC reservation for
  2022. The 2017 seats did include BC categories.
- **Per-GP statements (Form 15)** are published by each district collector on
  its own site, not by the SEC. `make collect-districts` searches the 30
  district sites and saves what it finds under `data/raw/districts/`. As of
  19 Oct 2026: 13 districts returned sarpanch reservation notices; 7 (Angul,
  Balasore, Bargarh, Cuttack, Deogarh, Nayagarh, Sundargarh) could not be
  reached through the proxy in three attempts; 10 returned none. Every
  statement is a scan printed in Odia; Kalahandi's has a text layer in a
  legacy non-Unicode Odia font, which reads as ASCII noise. Parsing them needs
  OCR. Several are superseded: the October 2021 lists include backward-class
  seats and were redrawn after the High Court's order of December 2021
  (redrafts dated 27-29 Dec 2021, finals January 2022). Ward-member (Form 13)
  drafts are not collected.
- **The SEC's "Report Of Last Three Elections" search**
  (`/Landing/ReservationList`) gives per-constituency reservation for the last
  three general elections. It asks for a name and a mobile number verified by
  OTP before it returns anything. The SEC's circular No. 1167 of May 2026 (in
  `data/raw/sec/files/table_013/`) describes this as the access route: a user
  gives name and mobile number and downloads each constituency's record as a
  PDF. Nothing here calls that search.

## Data

| File | Rows | Each row is |
|---|---:|---|
| [release/2017/sarpanch_winners.parquet](data/release/2017/sarpanch_winners.parquet) | 6,640 | a GP in the 2017 election and its elected sarpanch |
| [release/2022/sarpanch_winners.parquet](data/release/2022/sarpanch_winners.parquet) | 6,794 | a GP in the 2022 election and its elected sarpanch |

Columns: `year`, `district` (as printed in the district heading),
`block_serial` and `block` (Panchayat Samiti, as printed), `gram_panchayat`,
`winner` (as printed; null where the cell is blank), `winner_is_note` (true
where the cell records why no one was elected, such as "No Nomination",
"Countermanded", "Vacant" or a boycott), `winner_cell_merged` (true where one
printed cell spans several GPs and was copied to each), and `source_file`,
`source_page`, `source_row` (the PDF, the 1-based page and the table row).

Known defects in the sources, kept visible rather than repaired:

- 2022: the statewide PDF reprints 138 rows of Bargarh and Balasore after
  Bhadrak's last block (pp. 32-35), under Bhadrak's heading. They are dropped
  as reprints (same GP and winner printed earlier under another district).
- 2022: three GPs are printed twice with the same winner: Tikrapada (Komna,
  Nuapada) and Mustafapur and Khadipada (Dhamnagar, Bhadrak). Both districts
  still match the SEC's seat totals, so each repeat probably stands in for a GP
  missing from the list; matching district totals do not rule this out.
- 2017: the SEC site's Sambalpur link serves the Subarnapur file, so Sambalpur
  is missing. Malkangiri's file stops after its sixth block (18 GPs missing).
  Ganjam is 4 and Puri 1 short of the information book's GP counts.
- 2017: five winner cells are blank in the PDF.

```python
import pandas as pd

w22 = pd.read_parquet("data/release/2022/sarpanch_winners.parquet")
w22.groupby("district").size()
w22[w22["winner_is_note"]]
```

## Checks

`make check` runs ruff, recomputes every raw file's sha256 against the fetch
log, and runs these checks. An `external` check compares with a figure
published elsewhere; an `internal` one only shows the file agrees with itself.

<!-- checks:start -->

| Check | Appeals to | Status | Result |
| --- | --- | --- | --- |
| `2022_district_counts_vs_sec` | external | pass | Elected-sarpanch rows per district against the SEC's district-wise sarpanch reservation table of 8 Jan 2022 (read with pdftotext). 6,794 rows against 6,794 seats; 0 district(s) differ; unmatched names []. |
| `2022_key_unique` | internal | warn | 3 (district, block, GP) keys appear more than once (6 rows), kept as printed. |
| `2022_sec_table_women_share` | external | pass | In the SEC district table, women's seats (SCW + STW + RW) are 3,475 of 6,794 (51.15%); the Odisha Gram Panchayat Act reserves at least half for women. Backward-class seats: 0 (no BC column; the 2021 High Court order). This checks the reference table, not a per-GP file. |
| `2017_district_counts_vs_sec` | external | warn | Elected-sarpanch rows per district against GPs in the 2017 information book: 6,640 rows against 6,801 GPs; 4 district(s) differ. Sambalpur's link on the SEC site serves the Subarnapur file, and Malkangiri's file omits its seventh block; both are source gaps. |
| `2022_hand_check` | external | not_run | 0 of 30 sampled rows compared by eye with the PDF page; 0 disagree. |

<!-- checks:end -->

The 30-row hand check is in
[data/checks/hand_check_2022.csv](data/checks/hand_check_2022.csv): fill
`matches_pdf` with yes or no after comparing each row with its PDF page.

## Reproducing

```
make sync      # uv environment
make data      # parse the committed raw files, rebuild MANIFEST.json and the checks
make check     # ruff + hash and check verification
make collect   # network: fetch anything missing from data/raw/fetch_log.csv
```

A downloaded file byte-identical to one already saved is not kept; its row in
the fetch log names the kept copy in `duplicate_of`. Files are written only
inside `data/raw/`.

`data/raw/sec/files/unlisted/` holds six SEC PDFs that came from [in-
rolls/local_elections](https://github.com/in-rolls/local_elections)
(`data/odisha/raw/`), where nobody recorded a download URL. Their fetch-log
rows have `method=copy`, name the repository, commit and path in `copied_from`,
and leave `url` blank. They are 2017 reservation counts by district for
sarpanch, ward member, panchayat samiti member and chairman, the 2017 PRI
information book, and the 2013-15 ULB information book. The SEC's `table_064`
page links a file with the same name as the last one; the bytes have not been
compared.

`make check` needs `pdftotext` (poppler). The SEC and district sites refuse
connections from outside India; the collectors go through a SOCKS5 proxy set
in `ODISHA_PROXY` (default `socks5h://localhost:1080`).

## License

Code: MIT. The data are public records of the State Election Commission,
Odisha and the district collectorates of Odisha.
