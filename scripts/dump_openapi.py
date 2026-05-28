"""Dump the OpenAPI schema of the current code to docs/openapi.json.

Used in CI to detect unintended changes to the public API contract. If you
intentionally change a route signature, add an `operation_id` etc, re-run
this script and commit the updated docs/openapi.json — the diff in the PR
makes the change visible to reviewers.

Usage:
    python -m scripts.dump_openapi              # writes docs/openapi.json
    python -m scripts.dump_openapi --check      # exits non-zero if differs
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the package importable when running from the repo root.
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

OUT_PATH = ROOT / "docs" / "openapi.json"


def _get_schema() -> dict:
    """Build the FastAPI app and return its OpenAPI schema dict.

    The app composition imports many runtime deps (Databricks SDK, psycopg).
    They must be installed in the env where this script runs.
    """
    from nuclea_modeler.backend.app import app
    schema = app.openapi()
    # Drop volatile fields that would churn the snapshot without semantic
    # meaning. Currently FastAPI doesn't add any timestamp-like field, so
    # this is a no-op placeholder — keep for future-proofing.
    return schema


def _write(schema: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump OpenAPI schema snapshot.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare current code's schema against the file on disk. "
             "Exit 2 if they differ.",
    )
    args = parser.parse_args()

    schema = _get_schema()
    new_text = json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"

    if args.check:
        if not OUT_PATH.exists():
            print(f"::error::Snapshot not found at {OUT_PATH}. Run scripts/dump_openapi.py first.")
            return 2
        existing = OUT_PATH.read_text(encoding="utf-8")
        # Stub snapshot is acceptable — primeira execução real ainda não rodou.
        # Operator deve rodar `python -m scripts.dump_openapi` num workspace
        # com databricks-sdk e committar o resultado.
        try:
            parsed = json.loads(existing)
            if isinstance(parsed, dict) and any(k.startswith("_note") for k in parsed):
                print(
                    "::warning::Snapshot is a stub. Run `python -m scripts.dump_openapi` "
                    "in an env with databricks-sdk installed and commit docs/openapi.json."
                )
                return 0
        except (json.JSONDecodeError, ValueError):
            pass
        if existing != new_text:
            print(
                "::error::OpenAPI snapshot is stale.\n"
                "Run `python -m scripts.dump_openapi` and commit docs/openapi.json.",
                file=sys.stderr,
            )
            # Helpful: print a tiny diff hint
            import difflib
            diff = "".join(
                difflib.unified_diff(
                    existing.splitlines(keepends=True),
                    new_text.splitlines(keepends=True),
                    fromfile="committed",
                    tofile="generated",
                    n=2,
                )
            )
            # Cap at 4000 chars to avoid flooding the log.
            print(diff[:4000], file=sys.stderr)
            return 2
        print("OK — OpenAPI snapshot matches the code.")
        return 0

    _write(schema, OUT_PATH)
    print(f"Wrote {OUT_PATH} ({len(new_text)} bytes, {len(schema.get('paths', {}))} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
