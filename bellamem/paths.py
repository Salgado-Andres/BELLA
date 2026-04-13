"""Project-local path resolution for bellamem runtime state.

Runtime state (belief snapshot + embedder cache + LLM EW cache) lives in
`<project_root>/.graph/` by default, where `project_root` is resolved by:

    1. $BELLAMEM_PROJECT if set — explicit anchor, the escape hatch for
       non-git workflows and for Claude Code skills launched from a
       non-repo cwd like `C:\\Program Files\\Claude Code`.
    2. The git repo root, walking up from cwd.
    3. Cwd itself, as a last-resort fallback. A one-time stderr warning
       fires in this case so the fallback is visible — silent fallback
       to cwd was the root cause of #4 (bellamem writing .graph/ into
       the Claude Code install directory on Windows).

Each path respects its corresponding environment variable override:

    BELLAMEM_PROJECT              → project root anchor (directory)
    BELLAMEM_SNAPSHOT             → the belief graph snapshot (file)
    BELLAMEM_EMBEDDER_CACHE_PATH  → the on-disk embedding cache (file)
    BELLAMEM_EW_LLM_CACHE_PATH    → the LLM-backed EW cache (file)

Use BELLAMEM_PROJECT when you want one anchor that propagates to every
path (snapshot, caches, .env loader, Claude Code session discovery).
Use the per-file overrides when you want finer control.

Legacy state: prior versions stored these under `~/.bellamem/`. v0.0.3 does
NOT silently read from `~/.bellamem/` — that would re-introduce the
cross-project contamination the per-project graph is designed to fix. If
legacy files are detected, we emit a one-time warning per file pointing at
`bellamem migrate`, and return the project-local path regardless. Users
must explicitly migrate (or set `BELLAMEM_SNAPSHOT` themselves) to inherit
their old graph into a new project.

This module is a leaf utility: it imports only from stdlib and is safe to
import from both core/ and adapters/.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


_GRAPH_DIRNAME = ".graph"

LEGACY_DIR = Path("~/.bellamem").expanduser()
LEGACY_SNAPSHOT = LEGACY_DIR / "default.json"
LEGACY_EMBED_CACHE = LEGACY_DIR / "embed_cache.json"
LEGACY_LLM_EW_CACHE = LEGACY_DIR / "llm_ew_cache.json"

_warned_legacy: set[str] = set()
_warned_no_git = False


def project_root() -> Path:
    """Return the project anchor for bellamem runtime state.

    Resolution order:
      1. $BELLAMEM_PROJECT if set — explicit override.
      2. Walk up from cwd looking for a .git directory.
      3. Fall back to cwd, emitting a one-time stderr warning.

    The last-resort cwd fallback preserves backwards compatibility,
    but the warning makes the fallback visible so users with a non-repo
    cwd (e.g. Claude Code skills launched from `C:\\Program Files\\Claude
    Code` on Windows) don't silently accumulate .graph/ dirs in
    unexpected places. Fixes #4.
    """
    override = os.environ.get("BELLAMEM_PROJECT")
    if override:
        return Path(os.path.expanduser(override)).resolve()

    start = Path.cwd().resolve()
    for parent in (start, *start.parents):
        if (parent / ".git").exists():
            return parent

    global _warned_no_git
    if not _warned_no_git:
        _warned_no_git = True
        print(
            f"bellamem: no git repository found above {start} — "
            f"falling back to cwd for runtime state (.graph/, .env, "
            f"Claude Code session discovery). To pin bellamem to a "
            f"specific project, set BELLAMEM_PROJECT=/path/to/project. "
            f"See https://github.com/immartian/bellamem/issues/4.",
            file=sys.stderr,
        )
    return start


def graph_dir() -> Path:
    """`<project_root>/.graph/` — where new-style runtime state lives."""
    return project_root() / _GRAPH_DIRNAME


def _resolve(env_var: str, basename: str, legacy: Path) -> str:
    """Resolve a runtime-state file path.

    Resolution order:
      1. $env_var if set (explicit user override).
      2. <project_root>/.graph/<basename> — always, even if it doesn't
         exist yet (ingest will create it). Legacy state is NOT used as
         a read fallback: silently reading another project's graph is
         exactly the cross-project contamination we're trying to fix.

    If a legacy file exists alongside a fresh project path, we emit a
    one-time-per-basename warning pointing at `bellamem migrate`, so the
    user can inherit their old graph deliberately rather than by accident.
    """
    override = os.environ.get(env_var)
    if override:
        return os.path.expanduser(override)

    project_path = graph_dir() / basename

    if (
        not project_path.exists()
        and legacy.exists()
        and basename not in _warned_legacy
    ):
        _warned_legacy.add(basename)
        print(
            f"bellamem: legacy state found at {legacy} but not loaded. "
            f"Run `bellamem migrate` in this project to copy it into "
            f"{project_path}.",
            file=sys.stderr,
        )

    return str(project_path)


def default_snapshot_path() -> str:
    return _resolve("BELLAMEM_SNAPSHOT", "default.json", LEGACY_SNAPSHOT)


def default_embed_cache_path() -> str:
    return _resolve(
        "BELLAMEM_EMBEDDER_CACHE_PATH", "embed_cache.json", LEGACY_EMBED_CACHE
    )


def default_llm_ew_cache_path() -> str:
    return _resolve(
        "BELLAMEM_EW_LLM_CACHE_PATH", "llm_ew_cache.json", LEGACY_LLM_EW_CACHE
    )
