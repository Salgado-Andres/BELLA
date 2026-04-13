"""Tests for paths.project_root resolution.

Covers the three-tier resolution order added in #4 fix:
  1. BELLAMEM_PROJECT explicit override
  2. Git root walk from cwd
  3. Cwd fallback with visible warning
"""

import os
from pathlib import Path

import pytest

from bellamem import paths


@pytest.fixture(autouse=True)
def reset_warning_flag():
    """Each test starts with a fresh _warned_no_git so the one-time
    warning can be observed per-test instead of hiding across tests."""
    paths._warned_no_git = False
    yield
    paths._warned_no_git = False


def test_project_root_env_var_override(tmp_path, monkeypatch):
    """BELLAMEM_PROJECT explicitly pins project_root, skipping git walk."""
    # Build a non-git dir and point BELLAMEM_PROJECT at it.
    project = tmp_path / "pinned_project"
    project.mkdir()
    monkeypatch.setenv("BELLAMEM_PROJECT", str(project))
    monkeypatch.chdir(tmp_path)  # cwd is NOT the pinned project

    result = paths.project_root()
    assert result == project.resolve()


def test_project_root_env_var_expands_user(tmp_path, monkeypatch):
    """~ in BELLAMEM_PROJECT is expanded."""
    monkeypatch.setenv("BELLAMEM_PROJECT", "~")
    result = paths.project_root()
    assert result == Path(os.path.expanduser("~")).resolve()


def test_project_root_walks_to_git_root(tmp_path, monkeypatch):
    """Without BELLAMEM_PROJECT, project_root walks up for .git."""
    monkeypatch.delenv("BELLAMEM_PROJECT", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()  # fake git dir, existence is enough
    subdir = repo / "src" / "deep" / "inside"
    subdir.mkdir(parents=True)
    monkeypatch.chdir(subdir)

    result = paths.project_root()
    assert result == repo.resolve()


def test_project_root_fallback_warns_once(tmp_path, monkeypatch, capsys):
    """No env var and no git repo: fall back to cwd with a one-time warning."""
    monkeypatch.delenv("BELLAMEM_PROJECT", raising=False)
    non_repo = tmp_path / "no_git_here"
    non_repo.mkdir()
    monkeypatch.chdir(non_repo)

    result1 = paths.project_root()
    assert result1 == non_repo.resolve()
    err1 = capsys.readouterr().err
    assert "no git repository found" in err1
    assert "BELLAMEM_PROJECT" in err1

    # Second call: warning must NOT fire again in the same process.
    result2 = paths.project_root()
    assert result2 == non_repo.resolve()
    err2 = capsys.readouterr().err
    assert err2 == ""
