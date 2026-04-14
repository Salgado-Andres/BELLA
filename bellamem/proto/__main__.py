"""Subcommand dispatcher for `python -m bellamem.proto`.

    python -m bellamem.proto ingest [SNAPSHOT]   # run ingest on a session
    python -m bellamem.proto resume [--graph PATH]  # print typed summary

`python -m bellamem.proto.ingest` and `python -m bellamem.proto.resume`
are also directly runnable for their individual commands.
"""
from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python -m bellamem.proto <ingest|resume> [args...]",
              file=sys.stderr)
        return 2
    cmd = sys.argv[1]
    rest = sys.argv[2:]
    # rewrite argv so downstream main() sees the right shape
    sys.argv = [sys.argv[0]] + rest
    if cmd == "ingest":
        from bellamem.proto.ingest import main as ingest_main
        return ingest_main()
    if cmd == "resume":
        from bellamem.proto.resume import main as resume_main
        return resume_main()
    print(f"unknown subcommand: {cmd!r} (expected ingest | resume)",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
