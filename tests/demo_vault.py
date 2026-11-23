"""Demo vault used by the tests and the screenshots. All data is made up."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bwdedupe.demo import ITEMS  # noqa: E402

SECRETS = sorted({v for i in ITEMS for v in (i["login"]["password"], i["login"]["totp"], i["notes"]) if v}
                 | {"demo-field", "demo-passkey"})

if __name__ == "__main__":
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        json.dump(ITEMS, f, indent=1)
