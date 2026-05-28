"""Feature flags — env-driven, read once at startup, exposed via /api/features.

Design choices:
- Flags are boolean, default off. To enable a flag named `foo_bar`, set
  `NUCLEA_FEATURE_FOO_BAR=true` (or `1`, `yes`).
- The flag set is static (declared in `KNOWN_FLAGS` below) so /api/features
  returns a stable shape and the frontend can treat unknown flags as off.
- For dark-launches: ship the code behind a flag (default off), enable
  per-environment via env var, no redeploy needed for rollback.
- For multi-tenant or per-user gating: out of scope here — use GrowthBook /
  LaunchDarkly when that's needed. This module is for binary on/off rollouts.

Frontend usage (via /api/features):
    const { data: features } = useGetFeaturesSuspense();
    if (features.embarcadero_v2) { ... }
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Final


# Declared flags. Adding a flag here makes it appear in /api/features.
# Keep names snake_case ASCII.
KNOWN_FLAGS: Final[tuple[str, ...]] = (
    # ── Cross-cutting ───────────────────────────────────────────────────────
    "global_search_v2",        # next-gen search UI (placeholder)
    # ── Module 2 (Reverse Engineering) ──────────────────────────────────────
    "embarcadero_v2",          # next-gen .erx parser with namespace heuristics
    "ddl_import_dry_run",      # show DDL preview before persisting
    # ── Module 4 (DER) ─────────────────────────────────────────────────────
    "der_minimap",             # show minimap on the diagram canvas
    "der_auto_layout_v2",      # experimental dagre tweaks
    # ── Module 8 (Versioning) ──────────────────────────────────────────────
    "versions_signed",         # cryptographic signature on published versions
    # ── Module 9 (UC Sync) ─────────────────────────────────────────────────
    "sync_column_lineage",     # attempt to write column-level lineage tags
    # ── Operational ────────────────────────────────────────────────────────
    "structured_logs",         # legacy alias — controlled by NUCLEA_LOG_JSON now
)


_TRUTHY = {"true", "1", "yes", "on"}


def _env_key(flag: str) -> str:
    """Map a flag name to its env var: foo_bar → NUCLEA_FEATURE_FOO_BAR."""
    return f"NUCLEA_FEATURE_{flag.upper()}"


@lru_cache(maxsize=1)
def get_features() -> dict[str, bool]:
    """Read the current state of every declared flag.

    Cached at process startup. Changing env vars after boot requires a restart,
    which is the desired behaviour — we never want feature state to drift
    between requests served by the same worker.
    """
    return {flag: os.getenv(_env_key(flag), "").lower() in _TRUTHY for flag in KNOWN_FLAGS}


def is_enabled(flag: str) -> bool:
    """Boolean check for a single flag. Unknown flag names return False."""
    return get_features().get(flag, False)
