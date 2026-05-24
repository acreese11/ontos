#!/usr/bin/env python3
"""Enforce parity between bundle and marketplace OBO scope declarations.

Background
----------
Ontos can be deployed two ways:

  * Marketplace install — uses ``src/manifest.yaml``'s ``user_api_scopes``.
  * Bundle deploy — uses ``src/databricks.yaml``'s
    ``resources.apps.ontos.user_api_scopes``.

Until 2026-05, ``databricks.yaml`` declared no scopes at all. Bundle-deployed
apps then served OBO tokens with only the IAM defaults, which broke
Schema Importer and several other UC-touching features with a misleading
``Provided OAuth token does not have required scopes: unity-catalog`` error.

This check fails the build if the two files diverge.

Exit codes:
  0 — both files declare the same scope set (order-insensitive).
  1 — drift detected.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "src" / "manifest.yaml"
BUNDLE = REPO_ROOT / "src" / "databricks.yaml"

# Auto-applied by the Apps platform; declaring them in databricks.yaml is
# rejected by the update API. Allowed in manifest only.
IAM_DEFAULTS = {"iam.current-user:read", "iam.access-control:read"}


def info(msg: str) -> None:
    print(msg, flush=True)


def fail(msg: str) -> None:
    first_line, _, rest = msg.partition("\n")
    print(f"::error::{first_line}", file=sys.stderr, flush=True)
    if rest:
        print(rest, file=sys.stderr, flush=True)
    sys.exit(1)


def manifest_scopes() -> set[str]:
    doc = yaml.safe_load(MANIFEST.read_text())
    return set(doc.get("user_api_scopes") or [])


def bundle_scopes() -> set[str]:
    doc = yaml.safe_load(BUNDLE.read_text())
    apps = ((doc.get("resources") or {}).get("apps") or {})
    if not apps:
        return set()
    # Bundle declares exactly one app; take whichever key is present.
    app = next(iter(apps.values()))
    return set(app.get("user_api_scopes") or [])


def main() -> int:
    info("Comparing user_api_scopes between manifest.yaml and databricks.yaml…")
    manifest = manifest_scopes()
    bundle = bundle_scopes()

    # IAM defaults are platform-injected and must NOT appear in databricks.yaml.
    iam_in_bundle = bundle & IAM_DEFAULTS
    if iam_in_bundle:
        fail(
            "databricks.yaml declares IAM scopes that the Apps update API rejects:\n"
            + "\n".join(f"  - {s}" for s in sorted(iam_in_bundle))
            + "\n\nRemove them; the platform applies them automatically."
        )

    # The functional comparison: manifest minus IAM defaults must equal bundle.
    manifest_functional = manifest - IAM_DEFAULTS
    missing_from_bundle = manifest_functional - bundle
    extra_in_bundle = bundle - manifest_functional

    if not missing_from_bundle and not extra_in_bundle:
        info(f"      ok — {len(bundle)} scope(s) match.")
        return 0

    lines = ["Scope drift between manifest.yaml and databricks.yaml:"]
    if missing_from_bundle:
        lines.append("")
        lines.append("  In manifest but NOT in bundle (Boeing-style deploys won't get them):")
        for s in sorted(missing_from_bundle):
            lines.append(f"    - {s}")
    if extra_in_bundle:
        lines.append("")
        lines.append("  In bundle but NOT in manifest (marketplace installers won't get them):")
        for s in sorted(extra_in_bundle):
            lines.append(f"    - {s}")
    lines += [
        "",
        "Both deploy paths must declare the same user-delegated scopes so OBO tokens",
        "carry identical permissions regardless of install path. Update whichever file",
        "is behind so the sets match (excluding the platform-injected IAM defaults).",
    ]
    fail("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
