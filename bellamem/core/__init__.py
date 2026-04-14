"""bellamem.core — pure, domain-agnostic context memory.

This package must not import from bellamem.adapters. Keep it clean.
"""

from .gene import Belief, Gene, mass_of
from .bella import Bella, Claim, SELF_MODEL_FIELD, is_reserved_field
from .expand import expand, expand_before_edit
from .store import save, load
from .invariants import (
    ConflictRecord, TraversalRecord, record_omega_verification,
    qualify_for_anchor, add_conflict, add_traversal_record,
)

__all__ = [
    "Belief", "Gene", "mass_of",
    "Bella", "Claim", "SELF_MODEL_FIELD", "is_reserved_field",
    "expand", "expand_before_edit",
    "save", "load",
    "ConflictRecord", "TraversalRecord", "record_omega_verification",
    "qualify_for_anchor", "add_conflict", "add_traversal_record",
]
