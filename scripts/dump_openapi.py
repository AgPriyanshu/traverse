"""Write the app's OpenAPI document to a file.

Importing the app is equivalent to booting it for schema purposes and keeps the
CI drift check inside its time budget.
"""

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    from api.main import app

    destination = Path(argv[1] if len(argv) > 1 else "openapi.json")
    destination.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
    print(f"wrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
