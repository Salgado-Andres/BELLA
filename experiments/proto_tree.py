"""Prototype: tree+cross-edges project graph via per-turn cheap LLM.

Experiment scope (see memory/project_graph_shape_question.md):
  - Cross-session, single-project, single-user.
  - Conversation jsonl sources only (no code/doc ingestion).
  - Per-turn bounded-context LLM call, disk-cached.
  - Idempotent rebuild from cache.
  - Output: .graph/proto-tree.json (separate from .graph/default.json).

Not shipped code. Not wired into CLI. No effect on production bellamem
graph. Delete .graph/proto-tree*.json and this directory and nothing
else is touched.

Usage:
  python experiments/proto_tree.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROOT = Path('/media/im3/plus/labX/bellamem')
# Scratch/output lives under /tmp via tempfile — ratified rule:
# "scratch dirs go to /tmp via tempfile, never inside the project tree
# (durable feedback after the marketing/ near-miss)".
SCRATCH_DIR = Path(tempfile.gettempdir()) / 'bellamem-proto-tree'
OUTPUT_PATH = SCRATCH_DIR / 'proto-tree.json'
LLM_CACHE_PATH = SCRATCH_DIR / 'proto-tree-llm-cache.json'
EMBED_CACHE_PATH = SCRATCH_DIR / 'proto-tree-embed-cache.json'
CLAUDE_JSONL_DIR = Path('/home/im3/.claude/projects/-media-im3-plus-labX-bellamem')

LLM_MODEL = 'gpt-4o-mini'
EMBED_MODEL = 'text-embedding-3-small'
PROMPT_VERSION = 'v1'
CONTEXT_K = 8
RECENT_TURN_N = 3
DEDUP_COSINE = 0.85
MAX_TURN_CHARS = 1500
MAX_TURNS_PER_SESSION = 50  # cap for fast first run; bump or None for full

# Targeted run: process a specific turn slice of today's session to test
# the prompt against the architecture/walker/trichotomy content that lives
# later in the transcript. Set to None to use the default first-N behavior.
# The slice is (session_uuid_prefix, start_turn, end_turn).
TARGET_SLICE = ('853e838e', 500, 600)


# ---------------------------------------------------------------------------
# Env + OpenAI client
# ---------------------------------------------------------------------------

def _load_env() -> None:
    env = ROOT / '.env'
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_env()
from openai import OpenAI  # noqa: E402
CLIENT = OpenAI()


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Source:
    session_id: str
    turn_idx: int
    speaker: str
    jsonl_path: str
    text: str

    @property
    def id(self) -> str:
        return f'{self.session_id}#{self.turn_idx}'


@dataclass
class Concept:
    id: str
    topic: str
    class_: str  # invariant|decision|observation|ephemeral
    nature: str  # factual|normative|metaphysical
    parent: Optional[str]
    state: Optional[str]  # only for ephemerals
    embedding: np.ndarray = field(repr=False)
    source_refs: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            'id': self.id,
            'topic': self.topic,
            'class': self.class_,
            'nature': self.nature,
            'parent': self.parent,
            'state': self.state,
            'source_refs': self.source_refs,
        }


@dataclass
class Edge:
    type: str
    source: str
    target: str
    established_at: str
    confidence: str

    def to_json(self) -> dict:
        return {
            'type': self.type, 'source': self.source, 'target': self.target,
            'established_at': self.established_at, 'confidence': self.confidence,
        }


@dataclass
class ProtoGraph:
    concepts: dict[str, Concept] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    sources: dict[str, Source] = field(default_factory=dict)

    def _count_by(self, attr: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for c in self.concepts.values():
            v = getattr(c, attr)
            counts[v] = counts.get(v, 0) + 1
        return counts

    def to_json(self) -> dict:
        return {
            'prompt_version': PROMPT_VERSION,
            'concepts': {cid: c.to_json() for cid, c in self.concepts.items()},
            'edges': [e.to_json() for e in self.edges],
            'sources': {
                sid: {'session_id': s.session_id, 'turn_idx': s.turn_idx,
                      'speaker': s.speaker, 'preview': s.text[:200]}
                for sid, s in self.sources.items()
            },
            'stats': {
                'n_concepts': len(self.concepts),
                'n_edges': len(self.edges),
                'n_sources': len(self.sources),
                'by_class': self._count_by('class_'),
                'by_nature': self._count_by('nature'),
            }
        }


# ---------------------------------------------------------------------------
# jsonl parsing
# ---------------------------------------------------------------------------

def extract_text(msg: dict) -> str:
    c = msg.get('message', {}).get('content')
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = []
        for item in c:
            if isinstance(item, dict) and item.get('type') == 'text':
                parts.append(item.get('text', ''))
        return '\n'.join(parts)
    return ''


def read_session_turns(jsonl_path: Path) -> list[Source]:
    session_id = jsonl_path.stem[:8]
    turns: list[Source] = []
    idx = 0
    for line in jsonl_path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        t = rec.get('type')
        if t not in ('user', 'assistant'):
            continue
        text = extract_text(rec).strip()
        if not text:
            continue
        # Skip tool notifications and bracketed system messages
        if text.startswith('<') and '>' in text[:120]:
            continue
        turns.append(Source(
            session_id=session_id,
            turn_idx=idx,
            speaker=t,
            jsonl_path=str(jsonl_path),
            text=text[:MAX_TURN_CHARS],
        ))
        idx += 1
    return turns


# ---------------------------------------------------------------------------
# Embedding (cached)
# ---------------------------------------------------------------------------

_EMBED_CACHE: dict[str, list[float]] = {}


def _load_embed_cache() -> None:
    global _EMBED_CACHE
    if EMBED_CACHE_PATH.exists():
        _EMBED_CACHE = json.loads(EMBED_CACHE_PATH.read_text())


def _save_embed_cache() -> None:
    EMBED_CACHE_PATH.write_text(json.dumps(_EMBED_CACHE))


def embed(text: str) -> np.ndarray:
    key = hashlib.sha256(text.encode()).hexdigest()
    if key in _EMBED_CACHE:
        return np.array(_EMBED_CACHE[key], dtype=np.float32)
    resp = CLIENT.embeddings.create(model=EMBED_MODEL, input=text[:8000])
    v = list(resp.data[0].embedding)
    _EMBED_CACHE[key] = v
    return np.array(v, dtype=np.float32)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


# ---------------------------------------------------------------------------
# LLM call (cached)
# ---------------------------------------------------------------------------

_LLM_CACHE: dict[str, dict] = {}


def _load_llm_cache() -> None:
    global _LLM_CACHE
    if LLM_CACHE_PATH.exists():
        _LLM_CACHE = json.loads(LLM_CACHE_PATH.read_text())


def _save_llm_cache() -> None:
    LLM_CACHE_PATH.write_text(json.dumps(_LLM_CACHE))


SYSTEM_PROMPT = """You watch a developer/AI conversation and maintain a project concept graph for the bellamem project.

For each new turn, decide what the turn does to the graph.

A concept is identified by a short topic phrase (3-10 words) and classified on two axes:

class (temporal profile):
  - invariant: time-stable principles or structural facts; never expire
  - decision: revisable commitments ("we'll ship X before Y")
  - observation: factual claims about current state ("the bench scored N")
  - ephemeral: time-bound plans with a state machine (open/consumed/retracted/stale)

nature (epistemic type):
  - factual: measurable or checkable against reality
  - normative: commitments about how we SHOULD act or build
  - metaphysical: claims about what the system or its concepts ARE

The context you receive:
  - nearest_concepts: existing concepts in the graph relevant to this turn
  - open_ephemerals: ephemeral plans in this session still in "open" state
  - recent_turns: the last few turns for anaphora
  - current_turn: the turn to classify

Output strict JSON with:
  - act: "walk" | "add" | "none"
    "walk" = turn reacts to existing concepts (ratification, dispute, consume, retract)
    "add"  = turn introduces genuinely new standalone content
    "none" = procedural (question, meta-authorization, acknowledgment, tool notification)
  - cites: list of objects {"concept_id": "<id from nearest/ephemerals>", "edge": "<edge_type>"}
    edge types: voice-cross | support | dispute | elaborate | cause | retract | consume-success | consume-failure
  - creates: list of objects {"topic": "<3-8 word phrase>", "class": "<class>", "nature": "<nature>", "parent_hint": "<concept_id|null>"}
    Only create concepts for genuinely new ideas. Prefer citing existing concepts.
  - concept_edges: list of objects {"source": "<concept_id>", "target": "<concept_id>", "type": "<edge_type>", "confidence": "low|medium|high"}
    Edges BETWEEN concepts (not between turn and concept — those go in cites).

RULES:
- Questions → act=none
- Meta-authorization ("do whatever", "sure go", "I trust your call") → act=none
- Short acknowledgments ("thanks", "got it", "ok", "ya" alone) → act=walk with voice-cross IF the prior turn had a concrete proposal; otherwise act=none
- Retraction markers ("wait — hold on", "actually on reflection", "scratch that") → act=walk with retract cite
- Tool notifications, shell output, task-notification blocks → act=none
- Language-agnostic: classify by meaning, not keywords
- Topic phrases should be noun-phrase form, concise, and topic-slugable
- When in doubt between walk and none, prefer none
- Return ONLY valid JSON
"""

USER_TEMPLATE = """### nearest_concepts
{nearest}

### open_ephemerals
{ephemerals}

### recent_turns
{recent}

### current_turn
speaker: {speaker}
text: \"\"\"
{text}
\"\"\"

Output JSON only."""


def format_concepts(concepts: list[Concept]) -> str:
    if not concepts:
        return '(none)'
    return '\n'.join(
        f'- id="{c.id}" topic="{c.topic}" class={c.class_} nature={c.nature}'
        + (f' state={c.state}' if c.state else '')
        for c in concepts
    )


def format_turns(turns: list[Source]) -> str:
    if not turns:
        return '(none)'
    lines = []
    for t in turns:
        snippet = t.text[:300].replace('\n', ' ')
        if len(t.text) > 300:
            snippet += ' …'
        lines.append(f'T{t.turn_idx} [{t.speaker}]: {snippet}')
    return '\n'.join(lines)


def cache_key_for(turn: Source, context_ids: list[str], recent_ids: list[str]) -> str:
    h = hashlib.sha256()
    h.update(PROMPT_VERSION.encode())
    h.update(b'\x00')
    h.update(turn.text.encode())
    h.update(b'\x00')
    h.update(','.join(sorted(context_ids)).encode())
    h.update(b'\x00')
    h.update(','.join(recent_ids).encode())
    return h.hexdigest()


def call_llm(turn: Source, nearest: list[Concept],
             ephemerals: list[Concept], recent: list[Source]) -> tuple[dict, bool]:
    context_ids = [c.id for c in nearest] + [c.id for c in ephemerals]
    recent_ids = [s.id for s in recent]
    key = cache_key_for(turn, context_ids, recent_ids)
    if key in _LLM_CACHE:
        return _LLM_CACHE[key], True

    user = USER_TEMPLATE.format(
        nearest=format_concepts(nearest),
        ephemerals=format_concepts(ephemerals),
        recent=format_turns(recent),
        speaker=turn.speaker,
        text=turn.text,
    )
    try:
        resp = CLIENT.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': user},
            ],
            response_format={'type': 'json_object'},
            temperature=0.0,
        )
        raw = resp.choices[0].message.content or '{}'
        parsed = json.loads(raw)
    except Exception as e:
        print(f'  LLM error on turn {turn.id}: {e}')
        parsed = {'act': 'none', 'cites': [], 'creates': [], 'concept_edges': []}

    _LLM_CACHE[key] = parsed
    return parsed, False


# ---------------------------------------------------------------------------
# Graph update
# ---------------------------------------------------------------------------

def slugify(topic: str) -> str:
    s = re.sub(r'[^a-z0-9]+', '-', topic.lower()).strip('-')[:60]
    return s or 'unnamed'


def find_similar(graph: ProtoGraph, new_emb: np.ndarray,
                 new_topic: str) -> Optional[Concept]:
    cid = slugify(new_topic)
    if cid in graph.concepts:
        return graph.concepts[cid]
    best: Optional[Concept] = None
    best_sim = 0.0
    for c in graph.concepts.values():
        s = cosine(new_emb, c.embedding)
        if s > best_sim:
            best_sim = s
            best = c
    if best is not None and best_sim >= DEDUP_COSINE:
        return best
    return None


def apply_output(graph: ProtoGraph, turn: Source, output: dict) -> None:
    graph.sources[turn.id] = turn
    act = output.get('act', 'none')
    if act == 'none':
        return

    for cite in output.get('cites') or []:
        if not isinstance(cite, dict):
            continue
        cid = cite.get('concept_id') or cite.get('id')
        if not cid or cid not in graph.concepts:
            continue
        c = graph.concepts[cid]
        if turn.id not in c.source_refs:
            c.source_refs.append(turn.id)
        edge_type = cite.get('edge') or cite.get('edge_type', 'support')
        graph.edges.append(Edge(
            type=edge_type, source=turn.id, target=cid,
            established_at=turn.id,
            confidence=cite.get('confidence', 'medium'),
        ))
        if edge_type in ('consume-success', 'consume-failure'):
            c.state = 'consumed'
        elif edge_type == 'retract':
            c.state = 'retracted'

    for create in output.get('creates') or []:
        if not isinstance(create, dict):
            continue
        topic = (create.get('topic') or '').strip()
        if not topic:
            continue
        class_ = create.get('class', 'observation')
        nature = create.get('nature', 'factual')
        parent = create.get('parent_hint')

        new_emb = embed(topic)
        existing = find_similar(graph, new_emb, topic)
        if existing is not None:
            if turn.id not in existing.source_refs:
                existing.source_refs.append(turn.id)
            continue

        cid = slugify(topic)
        if cid in graph.concepts:
            cid = f'{cid}-{len(graph.concepts)}'
        graph.concepts[cid] = Concept(
            id=cid, topic=topic,
            class_=class_ if class_ in ('invariant', 'decision', 'observation', 'ephemeral') else 'observation',
            nature=nature if nature in ('factual', 'normative', 'metaphysical') else 'factual',
            parent=parent if (parent and parent in graph.concepts) else None,
            state='open' if class_ == 'ephemeral' else None,
            embedding=new_emb,
            source_refs=[turn.id],
        )

    for edge in output.get('concept_edges') or []:
        if not isinstance(edge, dict):
            continue
        src = edge.get('source')
        tgt = edge.get('target')
        if not src or not tgt:
            continue
        if src not in graph.concepts or tgt not in graph.concepts:
            continue
        graph.edges.append(Edge(
            type=edge.get('type', 'support'),
            source=src, target=tgt,
            established_at=turn.id,
            confidence=edge.get('confidence', 'medium'),
        ))


def assemble_context(graph: ProtoGraph, turn: Source,
                      all_turns_so_far: list[Source]) -> tuple[list[Concept], list[Concept], list[Source]]:
    if graph.concepts:
        turn_emb = embed(turn.text[:600])
        scored = [(cosine(turn_emb, c.embedding), c) for c in graph.concepts.values()]
        scored.sort(key=lambda x: x[0], reverse=True)
        nearest = [c for _, c in scored[:CONTEXT_K] if _ > 0.30]
    else:
        nearest = []

    ephemerals = []
    for c in graph.concepts.values():
        if c.class_ != 'ephemeral' or c.state != 'open':
            continue
        # Any source ref in the current session?
        for sr in c.source_refs:
            src = graph.sources.get(sr)
            if src and src.session_id == turn.session_id:
                ephemerals.append(c)
                break

    recent = all_turns_so_far[-RECENT_TURN_N:] if all_turns_so_far else []
    return nearest, ephemerals, recent


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    _load_embed_cache()
    _load_llm_cache()

    all_turns: list[Source] = []

    if TARGET_SLICE:
        # Targeted test: single session, explicit turn range
        uuid_prefix, start, end = TARGET_SLICE
        matches = [p for p in CLAUDE_JSONL_DIR.glob('*.jsonl')
                   if p.stem.startswith(uuid_prefix)]
        if not matches:
            print(f'No session matching prefix {uuid_prefix}')
            sys.exit(1)
        path = matches[0]
        print(f'TARGET_SLICE mode: {path.name} turns [{start}:{end}]')
        print()
        turns = read_session_turns(path)
        turns = turns[start:end]
        print(f'  {path.name[:20]}...: {len(turns)} turns in slice')
        all_turns.extend(turns)
    else:
        all_jsonls = sorted(
            CLAUDE_JSONL_DIR.glob('*.jsonl'),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if len(all_jsonls) < 2:
            print('Need at least 2 jsonl sessions')
            sys.exit(1)

        sessions = sorted(all_jsonls[:2], key=lambda p: p.stat().st_mtime)
        print('Sessions (chronological, older first):')
        for s in sessions:
            print(f'  {s.name} ({s.stat().st_size // 1024} KB)')
        print()

        for path in sessions:
            turns = read_session_turns(path)
            if MAX_TURNS_PER_SESSION:
                turns = turns[:MAX_TURNS_PER_SESSION]
            print(f'  {path.name[:20]}...: {len(turns)} turns')
            all_turns.extend(turns)

    print(f'Total turns to process: {len(all_turns)}')
    print()

    graph = ProtoGraph()
    stats = {'llm_calls': 0, 'cache_hits': 0, 'act_counts': {}}
    processed: list[Source] = []

    for i, turn in enumerate(all_turns):
        nearest, ephemerals, recent = assemble_context(graph, turn, processed)
        output, was_cached = call_llm(turn, nearest, ephemerals, recent)
        if was_cached:
            stats['cache_hits'] += 1
        else:
            stats['llm_calls'] += 1
        apply_output(graph, turn, output)
        processed.append(turn)

        act = output.get('act', 'none')
        stats['act_counts'][act] = stats['act_counts'].get(act, 0) + 1

        if (i + 1) % 10 == 0:
            _save_llm_cache()
            _save_embed_cache()
            print(f'  [{i+1}/{len(all_turns)}] concepts={len(graph.concepts)} '
                  f'edges={len(graph.edges)} llm={stats["llm_calls"]} '
                  f'cached={stats["cache_hits"]}')

    _save_llm_cache()
    _save_embed_cache()

    OUTPUT_PATH.write_text(json.dumps(graph.to_json(), indent=2))

    print()
    print('=' * 60)
    print('RESULT')
    print('=' * 60)
    print(f'concepts:   {len(graph.concepts)}')
    print(f'edges:      {len(graph.edges)}')
    print(f'sources:    {len(graph.sources)}')
    print(f'llm calls:  {stats["llm_calls"]}  (fresh)')
    print(f'cache hits: {stats["cache_hits"]}')
    print(f'acts:       {stats["act_counts"]}')
    print(f'by class:   {graph._count_by("class_")}')
    print(f'by nature:  {graph._count_by("nature")}')
    print(f'output:     {OUTPUT_PATH}')


if __name__ == '__main__':
    main()
