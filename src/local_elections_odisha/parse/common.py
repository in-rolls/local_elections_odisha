import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
RAW = DATA / "raw"
RELEASE = DATA / "release"


def clean(cell):
    """Collapse whitespace and line breaks inside a printed cell."""
    if cell is None:
        return None
    return re.sub(r"\s+", " ", cell).strip()


def fold(text):
    """Comparison key: ASCII letters and digits only, lower case."""
    t = unicodedata.normalize("NFKD", str(text))
    return re.sub(r"[^a-z0-9]", "", t.encode("ascii", "ignore").decode().lower())


def rel(path):
    return str(Path(path).resolve().relative_to(ROOT))
