"""v0.2 primitives: Source, Concept, Edge.

Design lives in memory/project_graph_v02_schema.md. Short version:

- Source: append-only pointer into a source file (typically a session
  jsonl turn). Never mutates. The grounding reference.
- Concept: topic-keyed project-model node, classified on two axes
  (class × nature). Ephemerals have a state machine; other classes
  have state=None.
- Edge: first-class typed relationship. BELLA R1 applies to edges —
  voices accumulate, confidence rises on re-ratification.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Literal, Optional

import numpy as np


# ---------------------------------------------------------------------------
# Jaynes / logit mass helpers — R1 accumulate for concepts
# ---------------------------------------------------------------------------

def _logit(p: float) -> float:
    """mass ∈ (0,1) → log-odds ∈ (-∞, ∞). Clamps to avoid infinity."""
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    """log-odds → mass ∈ (0, 1). Clamps to avoid overflow."""
    if x > 30:
        return 1.0 - 1e-6
    if x < -30:
        return 1e-6
    return 1.0 / (1.0 + math.exp(-x))


# Mass update deltas. New voice = strong evidence (different speaker
# ratifies the concept). Repeat voice = weak evidence (same speaker
# cites multiple times).
_MASS_DELTA_NEW_VOICE = 0.5     # ~1 step from 0.5 → 0.62
_MASS_DELTA_REPEAT_VOICE = 0.1  # tiny bump for repetition


ConceptClass = Literal["invariant", "decision", "observation", "ephemeral"]
ConceptNature = Literal["factual", "normative", "metaphysical"]
ConceptState = Literal["open", "consumed", "retracted", "stale"]
EdgeType = Literal[
    "support", "dispute", "cause", "elaborate",
    "voice-cross", "retract",
    "consume-success", "consume-failure",
]
Confidence = Literal["low", "medium", "high"]

_VALID_CLASSES = {"invariant", "decision", "observation", "ephemeral"}
_VALID_NATURES = {"factual", "normative", "metaphysical"}
_VALID_STATES = {"open", "consumed", "retracted", "stale"}
_VALID_EDGE_TYPES = {
    "support", "dispute", "cause", "elaborate",
    "voice-cross", "retract",
    "consume-success", "consume-failure",
}


def slugify_topic(topic: str) -> str:
    """Canonical concept ID from a topic phrase.

    Stable across runs / sessions / rebuilds — same topic string
    always produces the same slug, which is what makes cross-session
    concept identity deterministic.
    """
    s = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:60]
    return s or "unnamed"


@dataclass(frozen=True)
class Source:
    """Append-only pointer to a speaker turn in a session jsonl.

    Sources are immutable. The content stays in the file; Source
    carries just enough metadata to locate and label it.
    """
    session_id: str
    file_path: str
    speaker: str           # "user" | "assistant"
    turn_idx: int          # 0-based index among speaker turns in this session
    text: str              # the turn's content (kept here for context assembly)
    timestamp: Optional[float] = None

    @property
    def id(self) -> str:
        return f"{self.session_id}#{self.turn_idx}"

    def to_json(self) -> dict:
        return {
            "session_id": self.session_id,
            "file_path": self.file_path,
            "speaker": self.speaker,
            "turn_idx": self.turn_idx,
            "text_preview": self.text[:200],
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_json(cls, data: dict) -> "Source":
        return cls(
            session_id=data["session_id"],
            file_path=data.get("file_path", ""),
            speaker=data["speaker"],
            turn_idx=data["turn_idx"],
            text=data.get("text_preview", ""),
            timestamp=data.get("timestamp"),
        )


@dataclass
class Concept:
    """Topic-keyed project-model node.

    `id` is derived from a canonical slug of the topic — stable
    across runs, which gives cross-session concept identity without
    a UUID generator.

    **Mass** updates via BELLA R1 accumulate on each citation: a new
    voice (speaker not previously seen for this concept) bumps
    log-odds by _MASS_DELTA_NEW_VOICE; a repeat voice by the smaller
    _MASS_DELTA_REPEAT_VOICE. Mass starts at 0.5 (log-odds 0) and
    saturates toward 1.0 via sigmoid. Retractions can lower mass via
    negative deltas on the owning edge's endpoint (R5 convergence —
    deferred).
    """
    id: str
    topic: str
    class_: ConceptClass
    nature: ConceptNature
    parent: Optional[str] = None
    state: Optional[ConceptState] = None
    mass: float = 0.5
    mass_floor: float = 0.0
    voices: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    first_voiced_at: Optional[str] = None
    last_touched_at: Optional[str] = None
    embedding: Optional[np.ndarray] = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.class_ not in _VALID_CLASSES:
            raise ValueError(f"invalid class: {self.class_!r}")
        if self.nature not in _VALID_NATURES:
            raise ValueError(f"invalid nature: {self.nature!r}")
        if self.state is not None and self.state not in _VALID_STATES:
            raise ValueError(f"invalid state: {self.state!r}")
        if self.class_ != "ephemeral" and self.state is not None:
            raise ValueError(
                f"state is only valid for ephemeral class (got class={self.class_})"
            )
        if self.class_ == "ephemeral" and self.state is None:
            object.__setattr__(self, "state", "open")

    def cite(self, source_id: str, speaker: str = "") -> None:
        """Add a source citation and accumulate mass via R1.

        A citation does three things:
          1. Append the source_id (if not already present).
          2. Update first_voiced_at and last_touched_at.
          3. Bump mass via log-odds: stronger for a new speaker
             (ratification), weaker for repeat speakers (emphasis).

        Speaker is optional — when unknown, citations still update
        source_refs but don't move mass. This lets older code paths
        keep working without requiring a speaker at every call site.
        """
        if source_id in self.source_refs:
            return
        self.source_refs.append(source_id)
        if self.first_voiced_at is None:
            self.first_voiced_at = source_id
        self.last_touched_at = source_id

        if not speaker:
            return

        new_voice = speaker not in self.voices
        if new_voice:
            self.voices.append(speaker)
            delta = _MASS_DELTA_NEW_VOICE
        else:
            delta = _MASS_DELTA_REPEAT_VOICE
        new_log_odds = _logit(self.mass) + delta
        self.mass = _sigmoid(new_log_odds)

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "topic": self.topic,
            "class": self.class_,
            "nature": self.nature,
            "parent": self.parent,
            "state": self.state,
            "mass": self.mass,
            "mass_floor": self.mass_floor,
            "voices": list(self.voices),
            "source_refs": list(self.source_refs),
            "first_voiced_at": self.first_voiced_at,
            "last_touched_at": self.last_touched_at,
        }

    @classmethod
    def from_json(cls, data: dict) -> "Concept":
        return cls(
            id=data["id"],
            topic=data["topic"],
            class_=data["class"],
            nature=data["nature"],
            parent=data.get("parent"),
            state=data.get("state"),
            mass=data.get("mass", 0.5),
            mass_floor=data.get("mass_floor", 0.0),
            voices=list(data.get("voices", [])),
            source_refs=list(data.get("source_refs", [])),
            first_voiced_at=data.get("first_voiced_at"),
            last_touched_at=data.get("last_touched_at"),
        )


@dataclass
class Edge:
    """First-class typed relationship.

    Edge identity is derived from (type, source, target) — same
    semantic edge voiced twice accumulates voices instead of
    creating a duplicate node. That's BELLA R1 applied to edges.
    """
    type: EdgeType
    source: str            # source_id (turn) OR concept_id
    target: str            # always concept_id
    established_at: str    # source_id of the turn that first voiced this edge
    voices: list[str] = field(default_factory=list)
    confidence: Confidence = "medium"

    def __post_init__(self) -> None:
        if self.type not in _VALID_EDGE_TYPES:
            raise ValueError(f"invalid edge type: {self.type!r}")

    @property
    def id(self) -> str:
        h = hashlib.sha256()
        h.update(f"{self.type}|{self.source}|{self.target}".encode())
        return h.hexdigest()[:16]

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "source": self.source,
            "target": self.target,
            "established_at": self.established_at,
            "voices": list(self.voices),
            "confidence": self.confidence,
        }

    @classmethod
    def from_json(cls, data: dict) -> "Edge":
        return cls(
            type=data["type"],
            source=data["source"],
            target=data["target"],
            established_at=data["established_at"],
            voices=list(data.get("voices", [])),
            confidence=data.get("confidence", "medium"),
        )
