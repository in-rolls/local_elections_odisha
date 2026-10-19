"""Parse the SEC's lists of elected sarpanches, 2017 and 2022.

Both years use one layout: a ruled table with columns SL. NO., Panchayat
Samiti (block), Grama Panchayat and elected sarpanch, printed in Latin script.
The serial number and block are printed only on a block's first row and the
district only once, as a "DIST.-NAME" heading where it begins, so all three
are carried forward. 2022 is one statewide file; 2017 is one file per district.

A merged winner cell (pdfplumber returns None for the rows it covers) is
filled from the row above and flagged in `winner_cell_merged`. The last row
of a page sometimes lacks its bottom rule, so pdfplumber returns None for all
its cells; such a row is read by cropping each cell's area instead. The only merged
cells are notes such as "Boycott the 3-tier PRIs Election - 2017" spanning
GPs that share the note. Text in the winner column that is not a name is kept
as printed; `winner_is_note` marks it.

The lists carry no reservation category.

Run: python -m local_elections_odisha.parse.winners
"""

import re

import pandas as pd
import pdfplumber

from local_elections_odisha.parse.common import DATA, RAW, clean, fold, rel

SOURCES = {
    2022: sorted((RAW / "sec/files/table_057").glob("*SARPANCH.pdf")),
    2017: sorted((RAW / "sec/files/table_060").glob("*-S.P.pdf")),
}
DISTRICT = re.compile(r"DIST\.\s*-?\s*([A-Z][A-Z ]+)")
# Winner cells that record why no one was elected, not a person.
NOTE = re.compile(
    r"^(?:boycott|no nomination|countermand|election not held|vacant|postpone)",
    re.I,
)


def unbordered_cell(page, table, i, col):
    """Text of a cell pdfplumber could not close, e.g. the last row on a page
    whose bottom rule is missing; its box is the column's span in other rows
    times this row's height."""
    xs = next(r.cells[col] for r in table.rows if r.cells[col] is not None)
    y0, y1 = table.rows[i].bbox[1], table.rows[i].bbox[3]
    return page.crop((xs[0], y0, xs[2], y1)).extract_text()


def drop_reprinted(df):
    """Drop rows reprinted under a later district.

    The 2022 file repeats 138 rows of Bargarh (pp. 24-25) and Balasore
    (pp. 15-17) after Bhadrak's last block on p. 32, where they inherit
    Bhadrak's heading. A row is dropped when the same GP and winner were
    printed earlier in the file under a different district.
    """
    key = df["gram_panchayat"].map(fold) + "|" + df["winner"].fillna("").map(fold)
    first = df.groupby(key)["district"].transform("first")
    reprint = key.duplicated() & first.ne(df["district"])
    return df[~reprint], df[reprint]


def parse_file(path, year):
    out = []
    district = block = serial = None
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            heading = DISTRICT.search(page.extract_text() or "")
            if heading:
                district = heading.group(1).strip().title()
            for table in page.find_tables():
                prev_winner = None
                for rno, row in enumerate(table.extract(), start=1):
                    if len(row) != 4:
                        raise ValueError(f"{path.name} p{pno}: {len(row)} columns")
                    unbordered = row[2] is None
                    if unbordered:
                        row = [
                            unbordered_cell(page, table, rno - 1, c) if v is None else v
                            for c, v in enumerate(row)
                        ]
                    sl, blk, gp, winner = (clean(c) for c in row)
                    if sl in ("SL. NO.", "I.") or not gp:
                        continue
                    if sl:
                        serial = sl
                    if blk:
                        block = blk
                    # A winner cell is merged with the one above only in a row
                    # pdfplumber closed; an unbordered row was read by area.
                    merged = row[3] is None
                    if merged:
                        winner = prev_winner
                    prev_winner = winner
                    out.append(
                        {
                            "year": year,
                            "district": district,
                            "block_serial": serial,
                            "block": block,
                            "gram_panchayat": gp,
                            "winner": winner or None,
                            "winner_cell_merged": merged,
                            "source_file": rel(path),
                            "source_page": pno,
                            "source_row": rno,
                        }
                    )
    return out


def main():
    for year, files in SOURCES.items():
        if not files:
            raise SystemExit(f"no source files for {year}")
        df = pd.DataFrame([r for f in files for r in parse_file(f, year)])
        df, dropped = drop_reprinted(df)
        if len(dropped):
            where = dropped.groupby("source_page").size().to_dict()
            print(year, "dropped", len(dropped), "reprinted rows, by page:", where)
        df["winner_is_note"] = df["winner"].fillna("").str.contains(NOTE)
        (DATA / str(year)).mkdir(exist_ok=True)
        df.to_parquet(DATA / f"{year}/sarpanch_winners.parquet", index=False)
        print(year, len(df), "rows,", df["district"].nunique(), "districts")


if __name__ == "__main__":
    main()
