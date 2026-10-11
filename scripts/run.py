#!/usr/bin/env python3
"""Zero-install entrypoint for the skill-optimizer Agent Skill.

Usage (from any cwd):
  python path/to/skills-optimizer/scripts/run.py audit --project-root . --output reports
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    skill_root = Path(__file__).resolve().parents[1]
    if str(skill_root) not in sys.path:
        sys.path.insert(0, str(skill_root))
    from skill_optimizer.cli import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
