#!/usr/bin/env python3
"""Export FastAPI OpenAPI spec to docs/openapi.json.

Run without --check: regenerate and write the spec.
Run with --check: fail if committed spec differs from current app spec.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add src/ to path for import
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llm_wiki.api.app import app

OUTPUT_PATH = Path(__file__).parent.parent / "docs" / "openapi.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export the FastAPI OpenAPI spec to docs/openapi.json"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if spec has drifted from the committed version",
    )
    args = parser.parse_args()

    spec = app.openapi()
    spec_json = json.dumps(spec, indent=2, sort_keys=True) + "\n"

    if args.check:
        if not OUTPUT_PATH.exists():
            print(
                f"ERROR: {OUTPUT_PATH} not found. Run scripts/export_openapi.py to generate it.",
                file=sys.stderr,
            )
            return 1
        committed = OUTPUT_PATH.read_text(encoding="utf-8")
        if committed != spec_json:
            print(
                "ERROR: OpenAPI spec has drifted from committed docs/openapi.json",
                file=sys.stderr,
            )
            print("Run: python scripts/export_openapi.py", file=sys.stderr)
            print("Then commit the updated docs/openapi.json", file=sys.stderr)
            return 1
        print("OK: OpenAPI spec matches committed version")
        return 0

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(spec_json, encoding="utf-8")
    print(f"Exported OpenAPI spec to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
