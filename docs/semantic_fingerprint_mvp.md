# Semantic Fingerprint MVP

## Purpose
Detect semantic drift by defining rule meaning with test vectors instead of prose alone.

## New files
- bella/evaluator.py
- bella/semantic_fingerprint.py

## Modified files
- bella/anchor.py
- bella/session.py
- data/anchor.json

## Minimal features
1. Extract evaluation logic into a pure function
2. Add semantic fingerprint data types
3. Load fingerprints from anchor.json
4. Verify fingerprints on session init
5. Log semantic drift events
6. Add minimal tests

## Minimal founding rules
- FFT-001 silent bypass is forbidden
- C1 unregistered type fails

## Required tests
- stable kernel produces no semantic drift
- tampered anchor vectors raise integrity error
- amendment that changes behavior triggers semantic impact

## Constraints
- Keep patch additive
- Do not redesign BELLA core
- Keep implementation minimal
