#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Sync Cursor Other Models usage into config/budget.local.yaml.

Auth (personal Pro — no official Usage API):
  1. CURSOR_SESSION_TOKEN env (raw JWT or already-formed sub::jwt)
  2. Local Cursor state.vscdb key cursorAuth/accessToken

Primary fetch: GET https://cursor.com/api/usage-summary
  individualUsage.plan.apiPercentUsed  → Other Models pool
  individualUsage.plan.autoPercentUsed → Cursor Models pool (informational)

Fallback: POST https://cursor.com/api/dashboard/get-current-period-usage

Writes gitignored config/budget.local.yaml. Never prints the full token.
Unofficial dashboard endpoints may change; re-login in Cursor if auth fails.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _orchestrator_root() -> Path:
    """Directory that contains config/budget.yaml.

    Published layout (`npx skills add`): this file lives in <root>/scripts/.
    ORCHESTRATOR_ROOT wins when that directory already has the policy file
    (install_skill.ps1 points it at a full clone).
    """
    env = os.environ.get("ORCHESTRATOR_ROOT", "").strip().strip('"')
    if env:
        candidate = Path(env)
        if (candidate / "config" / "budget.yaml").is_file():
            return candidate
    return Path(__file__).resolve().parent.parent


REPO_ROOT = _orchestrator_root()
BUDGET_POLICY = REPO_ROOT / "config" / "budget.yaml"
BUDGET_LOCAL = REPO_ROOT / "config" / "budget.local.yaml"

USAGE_SUMMARY_URL = "https://cursor.com/api/usage-summary"
CURRENT_PERIOD_URL = "https://cursor.com/api/dashboard/get-current-period-usage"
AUTH_ME_URL = "https://cursor.com/api/auth/me"


def _die(msg: str, code: int = 1) -> None:
    print(f"sync_budget: {msg}", file=sys.stderr)
    raise SystemExit(code)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _b64url_json(segment: str) -> dict[str, Any]:
    pad = "=" * (-len(segment) % 4)
    raw = base64.urlsafe_b64decode(segment + pad)
    return json.loads(raw.decode("utf-8"))


def _jwt_sub(jwt: str) -> str:
    parts = jwt.split(".")
    if len(parts) < 2:
        _die("token does not look like a JWT")
    payload = _b64url_json(parts[1])
    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        _die("JWT missing sub claim")
    return sub


def _normalize_session_token(raw: str) -> tuple[str, str]:
    """Return (cookie_value, auth_source_label). Cookie = sub%3A%3Ajwt or sub::jwt."""
    token = raw.strip().strip('"').strip("'")
    if not token:
        _die("empty session token")
    # Already formed cookie (sub::jwt or URL-encoded)
    if "%3A%3A" in token:
        left, _, right = token.partition("%3A%3A")
        if left and right:
            return token, "env_formed"
    if "::" in token:
        left, _, right = token.partition("::")
        if left and right and right.count(".") >= 2:
            # Prefer URL-encoded form for Cookie header
            return f"{left}%3A%3A{right}", "env_formed"
    # Bare JWT
    if token.count(".") >= 2:
        sub = _jwt_sub(token)
        return f"{sub}%3A%3A{token}", "env_jwt"
    _die("unrecognized CURSOR_SESSION_TOKEN format (want JWT or sub::jwt)")


def _state_vscdb_paths() -> list[Path]:
    paths: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        paths.append(Path(appdata) / "Cursor" / "User" / "globalStorage" / "state.vscdb")
    home = Path.home()
    paths.append(home / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "state.vscdb")
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        paths.append(Path(xdg) / "Cursor" / "User" / "globalStorage" / "state.vscdb")
    paths.append(home / ".config" / "Cursor" / "User" / "globalStorage" / "state.vscdb")
    # Dedupe preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def _read_token_from_state_db(db_path: Path) -> str | None:
    if not db_path.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        cur = con.execute(
            "SELECT value FROM ItemTable WHERE key = ? LIMIT 1",
            ("cursorAuth/accessToken",),
        )
        row = cur.fetchone()
        if not row:
            return None
        val = row[0]
        if isinstance(val, bytes):
            val = val.decode("utf-8", errors="replace")
        if isinstance(val, str) and val.strip():
            return val.strip()
        return None
    except sqlite3.Error:
        return None
    finally:
        con.close()


def resolve_cookie() -> tuple[str, str]:
    env = os.environ.get("CURSOR_SESSION_TOKEN", "").strip()
    if env:
        cookie, label = _normalize_session_token(env)
        return cookie, label
    for path in _state_vscdb_paths():
        jwt = _read_token_from_state_db(path)
        if jwt:
            sub = _jwt_sub(jwt)
            return f"{sub}%3A%3A{jwt}", f"state.vscdb:{path}"
    _die(
        "no Cursor session found. Set CURSOR_SESSION_TOKEN or sign in to Cursor "
        "(state.vscdb cursorAuth/accessToken)."
    )


def _http_json(
    method: str,
    url: str,
    cookie: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None
    headers = {
        "Cookie": f"WorkosCursorSessionToken={cookie}",
        "Accept": "application/json",
        "User-Agent": "cursor-model-orchestrator-sync-budget/1.0",
    }
    if method == "POST":
        headers["Content-Type"] = "application/json"
        headers["Origin"] = "https://cursor.com"
        data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        _die(f"HTTP {e.code} from {url}: {detail}")
    except urllib.error.URLError as e:
        _die(f"network error calling {url}: {e.reason}")
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        _die(f"non-JSON response from {url}")
    if not isinstance(parsed, dict):
        _die(f"unexpected JSON type from {url}")
    return parsed


def _read_monthly_usd() -> float:
    if not BUDGET_POLICY.is_file():
        return 20.0
    text = BUDGET_POLICY.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped.startswith("other_models_monthly_usd:"):
            try:
                return float(stripped.split(":", 1)[1].strip())
            except ValueError:
                break
    return 20.0


def _extract_from_usage_summary(data: dict[str, Any]) -> dict[str, Any] | None:
    plan = (
        (data.get("individualUsage") or {}).get("plan")
        if isinstance(data.get("individualUsage"), dict)
        else None
    )
    if not isinstance(plan, dict):
        return None
    api = plan.get("apiPercentUsed")
    auto = plan.get("autoPercentUsed")
    if api is None and auto is None:
        return None
    return {
        "source": "usage-summary",
        "billing_cycle_start": data.get("billingCycleStart"),
        "billing_cycle_end": data.get("billingCycleEnd"),
        "membership_type": data.get("membershipType"),
        "api_percent_used": float(api if api is not None else 0.0),
        "auto_percent_used": float(auto if auto is not None else 0.0),
        "on_demand_enabled": bool(
            ((data.get("individualUsage") or {}).get("onDemand") or {}).get("enabled")
        ),
    }


def _extract_from_current_period(data: dict[str, Any]) -> dict[str, Any] | None:
    plan = data.get("planUsage")
    if not isinstance(plan, dict):
        # Some shapes nest under individualUsage
        iu = data.get("individualUsage")
        if isinstance(iu, dict) and isinstance(iu.get("plan"), dict):
            plan = iu["plan"]
        else:
            return None
    api = plan.get("apiPercentUsed")
    auto = plan.get("autoPercentUsed")
    if api is None and auto is None:
        return None
    return {
        "source": "get-current-period-usage",
        "billing_cycle_start": data.get("billingCycleStart"),
        "billing_cycle_end": data.get("billingCycleEnd"),
        "membership_type": data.get("membershipType"),
        "api_percent_used": float(api if api is not None else 0.0),
        "auto_percent_used": float(auto if auto is not None else 0.0),
        "on_demand_enabled": None,
    }


def fetch_usage(cookie: str) -> dict[str, Any]:
    summary = _http_json("GET", USAGE_SUMMARY_URL, cookie)
    extracted = _extract_from_usage_summary(summary)
    if extracted is None:
        period = _http_json("POST", CURRENT_PERIOD_URL, cookie, {})
        extracted = _extract_from_current_period(period)
    if extracted is None:
        _die("usage payload missing apiPercentUsed/autoPercentUsed")
    return extracted


def build_snapshot(usage: dict[str, Any], auth_source: str) -> dict[str, Any]:
    api = max(0.0, float(usage["api_percent_used"]))
    auto = max(0.0, float(usage["auto_percent_used"]))
    spent_ratio = min(api / 100.0, 1.0) if api <= 100 else api / 100.0
    # Cap display remaining at 0 when over 100%
    monthly = _read_monthly_usd()
    remaining = max(0.0, round(monthly * (1.0 - min(spent_ratio, 1.0)), 4))
    snap: dict[str, Any] = {
        "version": 1,
        "source": usage["source"],
        "auth_source": auth_source.split(":")[0],  # never full path with user home in committed docs; keep short in file
        "synced_at": _utcnow_iso(),
        "billing_cycle_start": usage.get("billing_cycle_start"),
        "billing_cycle_end": usage.get("billing_cycle_end"),
        "membership_type": usage.get("membership_type"),
        "api_percent_used": round(api, 6),
        "auto_percent_used": round(auto, 6),
        "spent_ratio": round(min(spent_ratio, 1.0) if api <= 100 else spent_ratio, 6),
        "remaining_usd": remaining,
        "other_models_monthly_usd": monthly,
        "stale": False,
    }
    if usage.get("on_demand_enabled") is not None:
        snap["on_demand_enabled"] = usage["on_demand_enabled"]
    # Store auth_source label without expanding secrets; path is OK for local file
    if auth_source.startswith("state.vscdb:"):
        snap["auth_source"] = "state.vscdb"
    else:
        snap["auth_source"] = auth_source
    return snap


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        if value == "":
            return '""'
        if any(c in value for c in ":#{}[]|&*!?>'\"%@`") or value.lower() in {
            "true",
            "false",
            "null",
            "yes",
            "no",
        }:
            return json.dumps(value)
        return value
    return json.dumps(value)


def write_budget_local(snap: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Auto-generated by scripts/sync_budget.py - do not commit",
        "# Other Models spend = api_percent_used; Cursor Models = auto_percent_used",
        "",
    ]
    order = [
        "version",
        "source",
        "auth_source",
        "synced_at",
        "billing_cycle_start",
        "billing_cycle_end",
        "membership_type",
        "api_percent_used",
        "auto_percent_used",
        "spent_ratio",
        "remaining_usd",
        "other_models_monthly_usd",
        "on_demand_enabled",
        "stale",
    ]
    for key in order:
        if key not in snap:
            continue
        lines.append(f"{key}: {_yaml_scalar(snap[key])}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync Cursor Other Models usage into budget.local.yaml")
    parser.add_argument("--print", dest="print_only", action="store_true", help="Print snapshot JSON, do not write")
    parser.add_argument("--force", action="store_true", help="Reserved; always fetches live usage")
    parser.add_argument(
        "--out",
        type=Path,
        default=BUDGET_LOCAL,
        help=f"Output path (default: {BUDGET_LOCAL})",
    )
    args = parser.parse_args(argv)

    cookie, auth_source = resolve_cookie()
    # Soft probe identity (optional; ignore failures)
    try:
        me = _http_json("GET", AUTH_ME_URL, cookie)
        email = me.get("email")
        if email and isinstance(email, str):
            # Do not print email in normal mode — privacy. Only confirm auth in stderr short form.
            print("sync_budget: authenticated", file=sys.stderr)
    except SystemExit:
        raise
    except Exception:
        pass

    usage = fetch_usage(cookie)
    snap = build_snapshot(usage, auth_source)

    if args.print_only:
        print(json.dumps(snap, indent=2, ensure_ascii=False))
        return 0

    write_budget_local(snap, args.out)
    print(
        f"sync_budget: wrote {args.out} "
        f"api_percent_used={snap['api_percent_used']} "
        f"spent_ratio={snap['spent_ratio']} "
        f"remaining_usd={snap['remaining_usd']} "
        f"source={snap['source']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
