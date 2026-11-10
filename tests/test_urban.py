import json
import shutil
from collections import Counter

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from local_elections_odisha.build import release, urban_contract
from local_elections_odisha.collect import urban_affidavits
from local_elections_odisha.parse import urban


def test_source_rebuild_preserves_typed_nulls_and_complete_keys(tmp_path):
    urban.build(tmp_path)
    table = pq.read_table(tmp_path / "winners.parquet")
    assert table.equals(pq.read_table(urban.RELEASE / "winners.parquet"))
    assert table.schema.field("winner_woman").type == pa.int8()
    assert table.schema.field("winner_woman").nullable
    assert table.schema.field("reserved_woman").type == pa.int8()
    assert table.schema.field("ward_no").type == pa.string()
    assert not table.schema.field("ward_no").nullable
    rows = table.to_pylist()
    assert len({(r["year"], r["body"], r["ward_no"]) for r in rows}) == 294
    assert all(
        r["winner_woman"] is None and r["winner_woman_raw"] is None for r in rows
    )
    historical = [r for r in rows if r["year"] == 2014]
    assert len(historical) == 126
    assert all(
        r["reserved_woman"] is None and r["reserved_caste"] is None for r in historical
    )
    current = [r for r in rows if r["year"] == 2022]
    assert sum(r["reserved_woman"] for r in current) == 85
    assert any(
        r["reserved_woman"] == 0 and r["reserved_caste"] == "NONE" for r in current
    )
    assert Counter(r["winner_party"] for r in current) == {
        "Biju Janata Dal": 116,
        "Bharatiya Janata Party": 24,
        "Indian National Congress": 9,
        "Independent": 19,
    }
    assert (
        next(
            r
            for r in current
            if r["body"].startswith("Cuttack") and r["ward_no"] == "8"
        )["winner"]
        == "NAMITA BARIK"
    )
    assert (
        next(
            r
            for r in historical
            if r["body"].startswith("Bhubaneswar") and r["ward_no"] == "67"
        )["winner"]
        == "Devi Prasad Nanda"
    )


def test_document_unit_downloads_and_timestamps_survive_roundtrip(tmp_path):
    original = pq.read_table(urban.RELEASE / "affidavit_documents.parquet")
    path = tmp_path / "documents.parquet"
    pq.write_table(original, path)
    table = pq.read_table(path)
    assert table.equals(original)
    assert table.schema.field("ward_no").type == pa.string()
    assert table.schema.field("downloaded_at").type == pa.timestamp("us", tz="UTC")
    assert table.schema.field("downloaded_bytes").type == pa.int64()
    rows = table.to_pylist()
    assert len(rows) == 365
    assert len({(r["year"], r["body"], r["document_serial"]) for r in rows}) == 365
    assert sum(r["office"] == "mayor" for r in rows) == 12
    assert all(r["ward_no"] is None for r in rows if r["office"] == "mayor")
    saved = [r for r in rows if r["download_status"] == "saved"]
    assert len(saved) == 55
    assert len({r["downloaded_path"] for r in saved}) == 54
    assert len({r["ward_no"] for r in saved}) == 42
    receipts = {
        r["document_serial"]: r
        for r in map(
            json.loads,
            (urban.SEARCH_LOG / "affidavits/receipts.jsonl").read_text().splitlines(),
        )
    }
    for row in saved:
        receipt = receipts[row["document_serial"]]
        assert row["downloaded_at"].isoformat() == receipt["fetched_at_utc"]
        assert row["downloaded_sha256"] == receipt["sha256"]
    links = urban_affidavits.frame()
    assert len(links) == 55
    assert {r["document_serial"] for r in links if r["ward_no"] == "1"} == {18, 19}


def test_manual_transcription_stays_hash_pinned(tmp_path):
    shutil.copytree(urban.MANUAL, tmp_path / "manual")
    path = tmp_path / "manual/corporators_2014_transcription.csv"
    path.write_text(path.read_text().replace("Mamata Rout", "Changed Name"))
    with pytest.raises(ValueError, match="transcription checksum mismatch"):
        urban.verify_sources(manual=tmp_path / "manual")


@pytest.mark.parametrize("defect", ["duplicate_key", "bool_sex", "unknown_caste"])
def test_contract_rejects_invalid_released_values(defect):
    table = pq.read_table(urban.RELEASE / "winners.parquet")
    if defect == "duplicate_key":
        rows = table.to_pylist()
        rows[1]["ward_no"] = rows[0]["ward_no"]
        table = pa.Table.from_pylist(rows, schema=urban.SCHEMA)
    elif defect == "bool_sex":
        index = table.schema.get_field_index("winner_woman")
        table = table.set_column(
            index, "winner_woman", pa.array([None] * len(table), type=pa.bool_())
        )
    else:
        rows = table.to_pylist()
        next(r for r in rows if r["year"] == 2022)["reserved_caste"] = "General"
        table = pa.Table.from_pylist(rows, schema=urban.SCHEMA)
    with pytest.raises(ValueError):
        urban_contract.validate_table(table, "winners")


def test_repository_verifier_rejects_urban_duplicate_key(tmp_path, monkeypatch):
    urban.build(tmp_path)
    path = tmp_path / "winners.parquet"
    rows = pq.read_table(path).to_pylist()
    rows[1]["ward_no"] = rows[0]["ward_no"]
    pq.write_table(pa.Table.from_pylist(rows, schema=urban.SCHEMA), path)
    monkeypatch.setattr(urban, "RELEASE", tmp_path)
    check = release.urban_check()
    assert check["blocking"] and check["status"] == "fail"
    assert "primary key" in check["detail"]
    with pytest.raises(SystemExit):
        release.verify()


def test_repository_verifier_rejects_value_tampering(tmp_path, monkeypatch):
    urban.build(tmp_path)
    path = tmp_path / "winners.parquet"
    rows = pq.read_table(path).to_pylist()
    rows[0]["winner"] = "Changed Name"
    pq.write_table(pa.Table.from_pylist(rows, schema=urban.SCHEMA), path)
    monkeypatch.setattr(urban, "RELEASE", tmp_path)
    check = release.urban_check()
    assert check["status"] == "fail" and "checksum" in check["detail"]


def test_generated_metadata_is_part_of_contract(tmp_path):
    urban.build(tmp_path)
    path = tmp_path / "dictionary.csv"
    path.write_text(path.read_text().replace("Election year", "Wrong year"))
    with pytest.raises(ValueError, match=r"dictionary|checksum"):
        urban.verify_release(tmp_path)
    metadata = json.loads((tmp_path / "schema.json").read_text())
    assert metadata["tables"]["winners"]["primary_key"] == ["year", "body", "ward_no"]
    fields = metadata["tables"]["winners"]["fields"]
    assert next(f for f in fields if f["name"] == "winner_woman")["nullable"] is True
