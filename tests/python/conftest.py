"""Makes the project tools importable from the tests."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for folder in ("tools", "data"):
    sys.path.insert(0, str(ROOT / folder))
