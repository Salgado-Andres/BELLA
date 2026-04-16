# AGENTS.md

## Project
This repository is an experimental fork of BELLA.

## Goal
Add an additive identity-memory layer to BELLA without redesigning BELLA core.

## Rules
- Do not rewrite BELLA core architecture unless required.
- Prefer additive modules and small patches.
- Preserve backward compatibility.
- Write tests for every new behavior.
- Keep changes minimal and reviewable.
- Start with the Semantic Fingerprint MVP only.

## MVP Scope
Implement only:
- pure evaluator extraction
- semantic fingerprint verification
- anchor fingerprint loading
- session init semantic drift check
- minimal tests

## Out of Scope
- UI
- graph database migration
- multi-agent orchestration
- broad refactors
- full productization

## Success Criteria
- Existing BELLA tests still pass
- New semantic fingerprint tests pass
- Semantic drift can be detected on session init
- Tampered fingerprint vectors are caught
