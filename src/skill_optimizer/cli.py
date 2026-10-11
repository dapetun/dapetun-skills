"""CLI for skill-optimizer."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from skill_optimizer import __version__
from skill_optimizer.apply_engine import apply_plan, rollback
from skill_optimizer.config import load_config
from skill_optimizer.pipeline import load_skills, run_audit, run_check, run_plan
from skill_optimizer.planner import plan_from_dict


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skill-optimizer",
        description="Audit, optimize, and safely maintain Agent Skills ecosystems",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    parser.add_argument("--config", type=Path, help="Path to YAML config")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root for project-scoped skill discovery (default: cwd)",
    )
    parser.add_argument(
        "--scope",
        action="append",
        choices=["user", "project", "builtin", "all"],
        help="Limit scopes (repeatable)",
    )
    parser.add_argument(
        "--platform",
        action="append",
        choices=["cursor", "claude", "codex", "agents", "all"],
        help="Limit platforms (repeatable)",
    )
    parser.add_argument(
        "--extra-root",
        action="append",
        type=Path,
        default=[],
        help="Extra skill root directory (repeatable)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports"),
        help="Output directory for reports (default: ./reports)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("audit", help="Diagnose skills without applying changes")
    sub.add_parser("plan", help="Build an optimization plan (read-only)")

    apply_p = sub.add_parser("apply", help="Apply an approved optimization plan")
    apply_p.add_argument(
        "--plan",
        type=Path,
        required=True,
        help="Path to optimization-plan.json",
    )
    apply_p.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview diffs without writing (default)",
    )
    apply_p.add_argument(
        "--execute",
        action="store_true",
        help="Actually write changes (requires --confirm)",
    )
    apply_p.add_argument(
        "--confirm",
        action="store_true",
        help="Required confirmation for non-dry-run apply",
    )
    apply_p.add_argument(
        "--only",
        action="append",
        default=[],
        help="Apply only these recommendation_id values (repeatable)",
    )

    check_p = sub.add_parser("check", help="Validate a single skill directory or SKILL.md")
    check_p.add_argument("skill_path", type=Path, help="Skill directory or SKILL.md path")

    rb = sub.add_parser("rollback", help="Restore skills from a snapshot")
    rb.add_argument("snapshot_id", help="Snapshot id under .skill-optimizer/snapshots/")

    return parser


def _make_config(args: argparse.Namespace):
    scopes = None
    if args.scope:
        scopes = []
        for s in args.scope:
            if s == "all":
                scopes = ["user", "project", "builtin"]
                break
            scopes.append(s)
    platforms = None
    if args.platform:
        platforms = []
        for p in args.platform:
            if p == "all":
                platforms = ["cursor", "claude", "codex", "agents"]
                break
            platforms.append(p)
    return load_config(
        args.config,
        project_root=args.project_root or Path.cwd(),
        platforms=platforms,
        scopes=scopes,
        extra_skill_roots=list(args.extra_root or []),
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    cfg = _make_config(args)
    output = Path(args.output).resolve()

    try:
        if args.command in {"audit", "plan"}:
            result = run_audit(cfg, output) if args.command == "audit" else run_plan(cfg, output)
            print(f"Skills: {len(result['skills'])}")
            print(f"Findings: {len(result['findings'])}")
            print(f"Plan: {result['plan'].plan_id}")
            print(f"Reports: {output}")
            for key, path in result["paths"].items():
                print(f"  - {key}: {path}")
            return 0

        if args.command == "check":
            result = run_check(cfg, args.skill_path, output)
            print(f"Checked: {result['skill'].name}")
            print(f"Structural issues: {len(result['skill'].structural_issues)}")
            print(f"Findings: {len(result['findings'])}")
            print(f"Reports: {output}")
            return 0 if not result["skill"].structural_issues else 1

        if args.command == "apply":
            plan_data = json.loads(Path(args.plan).read_text(encoding="utf-8"))
            plan = plan_from_dict(plan_data)
            skills = load_skills(cfg)
            dry_run = not bool(args.execute)
            result = apply_plan(
                plan,
                skills,
                cfg,
                dry_run=dry_run,
                confirm=bool(args.confirm),
                recommendation_ids=list(args.only) or None,
            )
            print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
            # Also write execution manifest copy into reports
            output.mkdir(parents=True, exist_ok=True)
            (output / "execution-manifest.json").write_text(
                json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            return 0 if result.ok else 2

        if args.command == "rollback":
            result = rollback(args.snapshot_id, cfg)
            print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
            return 0 if result.ok else 2

        parser.error(f"Unknown command {args.command}")
        return 2
    except Exception as exc:
        logging.getLogger(__name__).error("%s", exc)
        if args.verbose:
            raise
        return 1


if __name__ == "__main__":
    sys.exit(main())
