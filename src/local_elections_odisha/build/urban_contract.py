"""Schema, field definitions and invariants for the supplemental urban releases."""

from collections import Counter

import pyarrow as pa

BODY_COUNTS = {
    "Bhubaneswar Municipal Corporation": 67,
    "Cuttack Municipal Corporation": 59,
    "Berhampur Municipal Corporation": 42,
}


def field(name, arrow, description, *, nullable=False, values=None):
    return {
        "name": name,
        "arrow": arrow,
        "nullable": nullable,
        "description": description,
        "values": values,
    }


YEAR = field("year", pa.int16(), "Election year, not collection year.")
BODY = field("body", pa.string(), "Municipal corporation named by the source.")
WARD = field(
    "ward_no",
    pa.string(),
    "Printed ward identifier; not a cross-election geographic key.",
)
SOURCE = [
    field(
        "source_path",
        pa.string(),
        "Original source path relative to the repository root.",
    ),
    field(
        "source_sha256", pa.string(), "SHA-256 of the complete original source payload."
    ),
]
WINNER_FIELDS = [
    YEAR,
    BODY,
    WARD,
    field("winner", pa.string(), "Printed winner name, with whitespace normalized."),
    field(
        "winner_raw",
        pa.string(),
        "Unnormalized name cell or checked historical transcription.",
    ),
    field(
        "winner_basis", pa.string(), "Winner selection evidence.", values=["published"]
    ),
    field(
        "winner_party",
        pa.string(),
        "Printed party with whitespace normalized; absent in 2014.",
        nullable=True,
    ),
    field(
        "winner_party_raw",
        pa.string(),
        "Unnormalized party cell; absent in 2014.",
        nullable=True,
    ),
    field(
        "reserved_raw",
        pa.string(),
        "Original seat reservation cell; absent in 2014.",
        nullable=True,
    ),
    field(
        "reserved_caste",
        pa.string(),
        "Seat caste reservation; NONE means no caste reservation, not missing.",
        nullable=True,
        values=["NONE", "SC", "ST", "BC"],
    ),
    field(
        "reserved_woman",
        pa.int8(),
        "1 if women-reserved, 0 if not; null when the source does not state it.",
        nullable=True,
        values=[0, 1],
    ),
    field(
        "reserved_basis",
        pa.string(),
        "Evidence for the reservation fields.",
        values=["source_cell", "not_reported"],
    ),
    field(
        "winner_woman_raw",
        pa.string(),
        "Recorded person sex cell; unavailable in both winner sources.",
        nullable=True,
    ),
    field(
        "winner_woman",
        pa.int8(),
        "Recorded winner sex: 1 woman, 0 man, null unknown; "
        "never inferred from reservation.",
        nullable=True,
        values=[0, 1],
    ),
    field(
        "winner_woman_basis",
        pa.string(),
        "Evidence for winner sex; neither source records it.",
        values=["not_reported"],
    ),
    *SOURCE,
    field("source_page", pa.int16(), "One-based physical PDF page."),
    field(
        "source_column",
        pa.int16(),
        "One-based left/right table column in 2014; not applicable in 2022.",
        nullable=True,
    ),
    field(
        "source_row",
        pa.int16(),
        "One-based row within a 2014 column or 2022 extracted table, "
        "including table headers.",
    ),
    field(
        "extraction_method",
        pa.string(),
        "How the source row was read.",
        values=["visual_transcription", "pdf_table_text"],
    ),
    field(
        "raw_record_json",
        pa.string(),
        "Original PDF cells or historical transcription row as JSON.",
    ),
]
DOCUMENT_FIELDS = [
    YEAR,
    BODY,
    field(
        "document_serial",
        pa.int16(),
        "Printed directory ordinal; a document key, not a person identifier.",
    ),
    field("title", pa.string(), "Directory link text with whitespace normalized."),
    field("title_raw", pa.string(), "Unmodified text content of the directory link."),
    field(
        "office",
        pa.string(),
        "Office named in the filing label.",
        values=["mayor", "ward_councilor"],
    ),
    field(
        "ward_no",
        pa.string(),
        "Ward identifier from the directory label; null for mayor filings.",
        nullable=True,
    ),
    field(
        "candidate_label",
        pa.string(),
        "Candidate portion of the normalized directory label; "
        "copy/version suffixes retained.",
    ),
    field("document_url", pa.string(), "Original document href, including spaces."),
    field(
        "download_status",
        pa.string(),
        "Status in the retained receipt ledger.",
        values=["saved", "not_attempted", "failed"],
    ),
    field(
        "downloaded_path",
        pa.string(),
        "Canonical stored PDF path; byte-identical source links can share it.",
        nullable=True,
    ),
    field(
        "downloaded_sha256",
        pa.string(),
        "SHA-256 of the downloaded PDF.",
        nullable=True,
    ),
    field(
        "downloaded_bytes",
        pa.int64(),
        "Downloaded payload size in bytes.",
        nullable=True,
    ),
    field(
        "downloaded_at",
        pa.timestamp("us", tz="UTC"),
        "UTC request time from the original download receipt.",
        nullable=True,
    ),
    field(
        "pdf_pages",
        pa.int16(),
        "Readable PDF page count at acquisition.",
        nullable=True,
    ),
    *SOURCE,
]
CONTRACTS = {
    "winners": {
        "fields": WINNER_FIELDS,
        "primary_key": ["year", "body", "ward_no"],
        "rows": 294,
        "unit": "one published ward councilor per election, corporation and ward",
    },
    "affidavit_documents": {
        "fields": DOCUMENT_FIELDS,
        "primary_key": ["year", "body", "document_serial"],
        "rows": 365,
        "unit": "one affidavit document link; repeated filings remain distinct",
    },
}


def schema(name):
    return pa.schema(
        [
            pa.field(f["name"], f["arrow"], nullable=f["nullable"])
            for f in CONTRACTS[name]["fields"]
        ]
    )


def metadata():
    return {
        "format_version": 2,
        "scope": (
            "Supplemental urban sources; incomplete attributes do not satisfy "
            "the pooled master schema."
        ),
        "tables": {
            name: {
                "path": f"{name}.parquet",
                "unit": spec["unit"],
                "primary_key": spec["primary_key"],
                "rows": spec["rows"],
                "fields": [
                    {
                        **{k: v for k, v in f.items() if k != "arrow"},
                        "type": str(f["arrow"]),
                    }
                    for f in spec["fields"]
                ],
            }
            for name, spec in CONTRACTS.items()
        },
    }


def validate_table(table, name):
    spec = CONTRACTS[name]
    if not table.schema.equals(schema(name), check_metadata=False):
        raise ValueError(f"{name}: Arrow schema or nullability differs from contract")
    if table.num_rows != spec["rows"]:
        raise ValueError(f"{name}: unexpected row count")
    for f in spec["fields"]:
        column = table[f["name"]]
        if not f["nullable"] and column.null_count:
            raise ValueError(f"{name}: required field {f['name']} has nulls")
        if f["values"] is not None:
            observed = {v for v in column.to_pylist() if v is not None}
            if not observed.issubset(set(f["values"])):
                raise ValueError(f"{name}: invalid values in {f['name']}")
    records = table.to_pylist()
    keys = [tuple(r[k] for k in spec["primary_key"]) for r in records]
    if len(set(keys)) != len(keys) or any("" in key or None in key for key in keys):
        raise ValueError(f"{name}: missing or duplicated primary key")
    if name == "winners":
        validate_winners(records)
    else:
        validate_documents(records)


def validate_winners(records):
    expected = {
        (2014, b): n for b, n in BODY_COUNTS.items() if not b.startswith("Berhampur")
    }
    expected.update({(2022, b): n for b, n in BODY_COUNTS.items()})
    if Counter((r["year"], r["body"]) for r in records) != expected:
        raise ValueError("winners: unexpected body/year frame")
    for key, n in expected.items():
        wards = [r["ward_no"] for r in records if (r["year"], r["body"]) == key]
        if set(wards) != {str(i) for i in range(1, n + 1)}:
            raise ValueError("winners: incomplete ward frame")
    for r in records:
        if r["winner_woman"] is not None or r["winner_woman_raw"] is not None:
            raise ValueError("winners: adopted sources do not record winner sex")
        if r["year"] == 2014 and any(
            r[k] is not None
            for k in ["reserved_raw", "reserved_caste", "reserved_woman"]
        ):
            raise ValueError("winners: 2014 source does not record reservation")
        if r["year"] == 2022 and any(
            r[k] is None for k in ["reserved_raw", "reserved_caste", "reserved_woman"]
        ):
            raise ValueError("winners: missing reservation in complete 2022 source")


def validate_documents(records):
    if {r["document_serial"] for r in records} != set(range(1, 366)):
        raise ValueError("affidavit_documents: incomplete document frame")
    if {r["year"] for r in records} != {2022} or {r["body"] for r in records} != {
        "Bhubaneswar Municipal Corporation"
    }:
        raise ValueError("affidavit_documents: unexpected body/year")
    if Counter(r["office"] for r in records) != {"mayor": 12, "ward_councilor": 353}:
        raise ValueError("affidavit_documents: office counts changed")
    for r in records:
        if (r["office"] == "mayor") != (r["ward_no"] is None):
            raise ValueError("affidavit_documents: office/ward inconsistency")
        saved = r["download_status"] == "saved"
        attributes = [
            r[k]
            for k in [
                "downloaded_path",
                "downloaded_sha256",
                "downloaded_bytes",
                "downloaded_at",
                "pdf_pages",
            ]
        ]
        if saved and any(v is None for v in attributes):
            raise ValueError("affidavit_documents: saved document lacks receipt fields")
        if not saved and any(v is not None for v in attributes):
            raise ValueError(
                "affidavit_documents: unsaved document has download fields"
            )
    saved = [r for r in records if r["download_status"] == "saved"]
    if len(saved) != 55 or len({r["downloaded_path"] for r in saved}) != 54:
        raise ValueError("affidavit_documents: expected 55 links to 54 saved PDFs")
    if len({r["ward_no"] for r in saved}) != 42:
        raise ValueError("affidavit_documents: saved document coverage changed")
