# Odisha municipal corporation sources

This handoff contains 294 elected ward-councilor records: Bhubaneswar and Cuttack in 2014, and all three corporations covered by the SEC's 2022 winner publication. Mayors are not included in the winner file.

| Election | City | Winners | Reservation available | Recorded winner sex |
|---|---|---:|---:|---:|
| 2014 | Bhubaneswar | 67 | 0 | 0 |
| 2014 | Cuttack | 59 | 0 | 0 |
| 2022 | Bhubaneswar | 67 | 67 | 0 |
| 2022 | Cuttack | 59 | 59 | 0 |
| 2022 | Berhampur | 42 | 42 | 0 |

The 2014 names were manually transcribed and checked against the clearly legible original tables on physical PDF pages 71–72 (printed 59–60) of the already-held SEC 2013–15 information book. The source prints names and ward numbers, not sex or ward reservation. Its introduction dates the Bhubaneswar election January 8, 2014 and Cuttack election February 6, 2014. The historical book remains at `data/raw/sec/files/unlisted/INFORMATION-OF-G.E-TO-ULB-2013-14-14-15-1.pdf`; it was not copied. `data/manual/urban/transcription_receipt.json` pins the source and transcription hashes. The CSV is retained under `data/manual/urban/` with its original input headers. Original spellings are retained, including apparent typographical errors.

The [official 2022 corporator publication](https://sec.odisha.gov.in/wp-content/uploads/2023/02/NAME-OF-ELECTED-CORPORATORS.pdf) was recovered through Internet Archive's May 4, 2023 capture. The seven-page original prints all 168 winners, their parties and reservation categories. The offline table parser retains page, row and raw cells. Its 85 women-reserved wards comprise 34 in Bhubaneswar, 30 in Cuttack and 21 in Berhampur. Reservation is a seat attribute: the winner's sex remains null even in a women-reserved seat.

The original [2022 election report](https://sec.odisha.gov.in/wp-content/uploads/2023/11/ULBs_Final-2022-12-10-2023-FINAL_compressed.pdf), 229 PDF pages, was recovered from a February 8, 2024 capture. It documents March 24, 2022 polling and March 26 counting; it also records submission of corporation delimitation/reservation notifications on January 28, 2022. SEC Order 1768 of February 2, 2022 discusses final ward-division notifications. These sources do not establish unchanged geography between 2014 and 2022. Equal ward counts are not a crosswalk. No geographic transition or post-quota effect is estimated here, and 2014 reservation and independently recorded winner sex remain missing.

## Bhubaneswar affidavits

The live [municipal disclosure directory](https://www.bmc.gov.in/public-disclosure/1273) supplies 365 document links: 353 councilor filings spanning all 67 wards and 12 mayor filings. This is a document index, not a count of distinct or finally contesting candidates. Multiple filings for a person remain separate. Both offices are retained in the index and explicitly labeled; only councilor documents were downloaded in this pass.

A bounded collection selected filings with the same ward and exact normalized winner name, ignoring case, punctuation, spaces and trailing document-copy numbers. It recovered all 55 selected documents for 42 winners, totaling 54 distinct PDFs and 295,112,207 stored bytes. One byte-identical duplicate is retained once with both source receipts. The full directory remains available for reviewing the remaining spellings, ambiguous matches and absent winner labels. No fuzzy match was silently accepted.

Original scans are in `data/raw/sec/urban/affidavits/`; `data/search_log/urban/affidavits/receipts.jsonl` records URLs, times, hashes, page counts and canonical stored paths. The collector recomputes its deterministic selection from the released winner and document tables; no duplicate generated frame is stored. The typed index exposes `download_status`, `downloaded_path`, `downloaded_sha256`, `downloaded_bytes`, `downloaded_at` and `pdf_pages`. Each file is checked for PDF content and readable pages. The collector resumes from verified receipts and uses two workers. A browser User-Agent and official Referer succeeded after a plain request to the CMS returned 403; TLS verification stayed enabled.

A visually checked pilot, document 19, is a 20-page filing by Mihir Kumar Rout for ward 1. It states age 41 and describes an independent candidacy, whereas the winner publication identifies a BJD winner of that name. This illustrates why filing versions and party status require review. The text states the relationship to a parent; no demographic variable has been populated from the scan or photograph. These PDFs are retained evidence for subsequent attribute extraction, not automatically validated winner attributes.

## Outputs and handling

`data/release/urban/winners.parquet` has one row per `(year, body, ward_no)`. The `body` is the full printed corporation name and `ward_no` is a string identifier. `winner_woman` and `reserved_woman` are nullable Int8 values: 1, 0, or null. `reserved_caste` uses `NONE`, `SC`, `ST`, or `BC`; `NONE` means no caste reservation, whereas null means unavailable. `winner`, `winner_raw`, `winner_woman_raw`, `reserved_raw`, and explicit basis fields keep people, seats, and source readings distinct. Historical reservation/party and all winner-sex values remain null.

`affidavit_documents.parquet` has one row per `(year, body, document_serial)`, not one row per person. The serial is an integer directory ordinal, ward identifiers are strings, mayor ward IDs are null, and `downloaded_at` is a UTC timestamp. Only saved PDFs have download attributes. Both normalized and original link labels remain available.

The generated `dictionary.csv` and `schema.json` sit beside these tables and come from the same code contract, including fields, Arrow types, nullability, allowed values, units and primary keys. `profile.json`, `sources.json` and `checksums.json` are also generated. `sources.json` pins every input, including the manual transcription and acquisition receipts. These incomplete supplemental records are not forced into the pooled master schema: absent district identifiers, source commits or demographic fields are not invented.

Original sources remain under `data/raw/`; manual readings and their pins under `data/manual/urban/`; acquisition receipts and unsuccessful-route notes under `data/search_log/urban/`. The repository-wide `data/raw/fetch_log.csv` registers original payloads and byte-identical duplicates. [The relocation and field map](../../../docs/urban_renames.json) records the previous paths/names and their replacement; no compatibility copies remain. Internet Archive recovery used the standard `wayback` package; no private or OTP-protected reservation endpoint was used.

From the repository root:

```sh
make urban-data
make urban-check
make check
make urban-affidavits
```

`urban-data` is offline. `urban-affidavits` makes network requests only for missing or invalidated files in the saved exact-name selection. Broader collection requires an explicit change to that selection. The existing release manifest includes both urban tables. `make check` validates their hashes, schemas, nullability, primary keys, source pins and generated metadata; it fails on urban tampering. Focused tests also cover typed nulls, round trips, the 365-document/55-download/54-file counts, and rejection of invalid keys/types. The existing rural data files are unchanged.
