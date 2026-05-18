"""Safe Skies — synthetic aviation data generators for the DAIS 2026 demo.

Modeled against OAG, Cirium, OpenSky, and ICAO/FAA field shapes. See
`plans/dais-aviation-data-research.md` for the field-level source-of-truth and
`plans/dais-domain-model.md` for the domain/product/contract structure.

Public entry points:
    SERVICE_DATE — the target service date all generators are anchored to
    DEFAULT_SEED — RNG seed for reproducible runs
    generate_all() — orchestrator producing every table as a Polars DataFrame
"""
from __future__ import annotations

from datetime import date

SERVICE_DATE: date = date(2026, 6, 15)
DEFAULT_SEED: int = 42
