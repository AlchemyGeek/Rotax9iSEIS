"""
contract.py — envelope objects shared by every operation result
(Spec 01 §8.1): Provenance, Diagnostic, and the diagnostic catalog.

Pure — no I/O, no clock reads. Callers (the analyze_* operations) supply
the engine version, hash inputs, and timestamps; this module only shapes
and validates them.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional, Union

# The contract's own semantic version, independent of the toolkit's
# __version__ (Spec 01 R4 / Q7). Bump only when the shape of a result
# object or the diagnostic catalog changes.
CONTRACT_VERSION = "0.1.0"

DIAGNOSTIC_CATALOG = (
    "INGEST_UNKNOWN_FORMAT",
    "INGEST_GROUND_SESSION",
    "INGEST_DUPLICATE_OF",
    "INGEST_MULTI_POWER_CYCLE",
    "INGEST_MISSING_CHANNEL",
    "INGEST_SIGNAL_GAP",
    "PHASE_TAKEOFF_NOT_DETECTED",
    "PHASE_NO_CLIMB",
    "PHASE_NO_CRUISE",
    "BASELINE_LOW_N",
    "MODEL_INSUFFICIENT_DATA",
    "ENGINE_PLACEHOLDER_CONFIG",
    "ENGINE_CUSTOM_OVERRIDE",
    "RULES_SCHEMA_ERROR",
)

Severity = str    # "info" | "warn" | "error"
Scope = str       # "file" | "flight" | "fleet" | "topic"


def content_hash(obj) -> str:
    """
    SHA-256 of an object's canonical JSON form (sorted keys, no
    whitespace), hex-encoded. Used for profile_hash/params_hash/
    rules_hash so identical inputs always hash identically regardless of
    dict insertion order.
    """
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: Severity
    scope: Scope
    message: str
    refs: Optional[dict[str, Union[str, int]]] = None

    def __post_init__(self):
        if self.code not in DIAGNOSTIC_CATALOG:
            raise ValueError(f"Unknown diagnostic code: {self.code!r}")
        if self.severity not in ("info", "warn", "error"):
            raise ValueError(f"Invalid diagnostic severity: {self.severity!r}")
        if self.scope not in ("file", "flight", "fleet", "topic"):
            raise ValueError(f"Invalid diagnostic scope: {self.scope!r}")

    def to_dict(self) -> dict:
        d = {"code": self.code, "severity": self.severity, "scope": self.scope, "message": self.message}
        if self.refs is not None:
            d["refs"] = self.refs
        return d


@dataclass(frozen=True)
class EngineProfileRef:
    id: str
    hash: str
    source_status: str  # "VERIFIED" | "PLACEHOLDER" | "CUSTOM"

    def to_dict(self) -> dict:
        return {"id": self.id, "hash": self.hash, "source_status": self.source_status}


def engine_profile_ref(engine_config: dict, name: str) -> EngineProfileRef:
    """Build an EngineProfileRef from a loaded engine config dict."""
    source_status = engine_config.get("_metadata", {}).get("source_status", "VERIFIED")
    return EngineProfileRef(id=name, hash=content_hash(engine_config), source_status=source_status)


@dataclass(frozen=True)
class Provenance:
    engine_version: str
    engine_profile: EngineProfileRef
    params_hash: str
    source_keys: list[str] = field(default_factory=list)
    schema_version: str = CONTRACT_VERSION
    rules_hash: Optional[str] = None

    def to_dict(self) -> dict:
        d = {
            "engine_version": self.engine_version,
            "schema_version": self.schema_version,
            "engine_profile": self.engine_profile.to_dict(),
            "params_hash": self.params_hash,
            "source_keys": list(self.source_keys),
        }
        if self.rules_hash is not None:
            d["rules_hash"] = self.rules_hash
        return d
