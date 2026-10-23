"""Draw the 30-row sample of 2022 winners for checking by eye against the PDF.

Writes data/checks/hand_check_2022.csv with an empty `matches_pdf` column for
the checker to fill with yes or no. It refuses to overwrite a file that has
any answers in it. `make verify` reports the check as not_run until every row
is answered.

Run: python -m local_elections_odisha.build.hand_check
"""

import csv

import pandas as pd

from local_elections_odisha.build.release import HAND_CHECK
from local_elections_odisha.parse.common import DATA

SEED = 20261018
COLUMNS = ["district", "block", "gram_panchayat", "winner", "source_page"]


def main():
    if HAND_CHECK.exists():
        rows = list(csv.DictReader(HAND_CHECK.open(encoding="utf-8")))
        if any(r["matches_pdf"] for r in rows):
            raise SystemExit(f"{HAND_CHECK} already has answers; not overwriting")
    df = pd.read_parquet(DATA / "release/2022/sarpanch_winners.parquet")
    sample = df.sample(30, random_state=SEED).sort_values("source_page")
    sample = sample[[*COLUMNS, "source_row"]].assign(matches_pdf="")
    HAND_CHECK.parent.mkdir(exist_ok=True)
    sample.to_csv(HAND_CHECK, index=False)
    print(f"wrote {HAND_CHECK}")


if __name__ == "__main__":
    main()
