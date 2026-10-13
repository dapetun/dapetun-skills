#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fetch Cursor models & pricing docs and refresh config/models.generated.yaml.

Soft-fails: on parse/network errors, keeps the previous file and exits non-zero.

Privacy: downloads public Cursor documentation only. Does not collect, upload,
or log end-user personal data, prompts, or secrets.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

SOURCE_URLS = (
    "https://cursor.com/docs/models-and-pricing.md",
    "https://cursor.com/docs/models-and-pricing",
)
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "config" / "models.generated.yaml"

LOGICAL_SEED = {
    "cursor.auto_or_composer": {
        "display": "Auto / Composer 2.5",
        "pool": "cursor",
        "candidates": ["Auto", "Composer 2.5"],
    },
    "cursor.composer": {
        "display": "Composer 2.5",
        "pool": "cursor",
        "candidates": ["Composer 2.5"],
    },
    "cursor.grok_flagship": {
        "display": "Grok 4.7",
        "pool": "cursor",
        "candidates": ["Grok 4.7", "Grok 4.6", "Grok 4.5"],
    },
    "other.sonnet_strong": {
        "display": "Claude Sonnet 5",
        "pool": "other",
        "candidates": ["Claude Sonnet 5", "Claude Sonnet 5.5"],
    },
    "other.opus": {
        "display": "Claude Opus 5",
        "pool": "other",
        "candidates": ["Claude Opus 5", "Claude Opus 5.5"],
    },
    "other.sol": {
        "display": "GPT-5.6 Sol",
        "pool": "other",
        "candidates": ["GPT-5.6 Sol"],
    },
    "other.terra": {
        "display": "GPT-5.6 Terra",
        "pool": "other",
        "candidates": ["GPT-5.6 Terra"],
    },
    "other.luna": {
        "display": "GPT-5.6 Luna",
        "pool": "other",
        "candidates": ["GPT-5.6 Luna"],
    },
    "other.fable": {
        "display": "Claude Fable 5.1",
        "pool": "other",
        "hitl_required": True,
        "candidates": ["Claude Fable 5.1", "Claude Fable 5"],
    },
    "other.gemini_pro": {
        "display": "Gemini 3.1 Pro",
        "pool": "other",
        "candidates": ["Gemini 3.1 Pro"],
    },
    "other.gemini_flash": {
        "display": "Gemini 3.8 Flash",
        "pool": "other",
        "candidates": ["Gemini 3.8 Flash"],
    },
}


def fetch_text(url: str, timeout: int = 45) -> str:
    req = Request(url, headers={"User-Agent": "cursor-model-orchestrator-sync/0.1"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _money(cell: str) -> float | None:
    cell = cell.strip()
    if cell in {"-", "—", ""}:
        return None
    m = re.search(r"([\d.]+)", cell.replace(",", ""))
    return float(m.group(1)) if m else None


def _clean_name(cell: str) -> str:
    """Strip markdown links: [Grok 4.7](url) -> Grok 4.7."""
    cell = cell.strip()
    m = re.fullmatch(r"\[([^\]]+)\]\([^)]+\)", cell)
    return m.group(1).strip() if m else cell


def parse_price_rows(text: str) -> list[dict]:
    """Parse markdown tables: Model | Provider | Input | Cache write | Cache read | Output | Notes."""
    rows: list[dict] = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) < 6:
            continue
        name, provider = _clean_name(cols[0]), _clean_name(cols[1])
        if name.lower() in {"model", "name"} or set(name) <= {"-"}:
            continue
        if provider.lower() in {"provider"} or set(provider) <= {"-"}:
            continue
        inp = _money(cols[2])
        out = _money(cols[5]) if len(cols) > 5 else _money(cols[-2])
        if inp is None or out is None:
            continue
        # Skip plan tables (Pro / Ultra)
        if name in {"Pro", "Pro Plus", "Ultra", "Start (India only)", "Hobby"}:
            continue
        rows.append(
            {
                "name": name,
                "provider": provider,
                "input_per_m": inp,
                "output_per_m": out,
            }
        )
    return rows


def split_pools(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    cursor, other = [], []
    for r in rows:
        prov = r.get("provider", "").lower()
        name = r.get("name", "")
        if prov == "cursor" or name.startswith("Grok") or name.startswith("Composer"):
            cursor.append(
                {
                    "name": name,
                    "input_per_m": r["input_per_m"],
                    "output_per_m": r["output_per_m"],
                }
            )
        else:
            other.append(
                {
                    "name": name,
                    "input_per_m": r["input_per_m"],
                    "output_per_m": r["output_per_m"],
                }
            )
    return cursor, other


def refresh_logical_displays(logical: dict, rows: list[dict]) -> dict:
    names = {r["name"] for r in rows}
    out = {}
    for key, meta in logical.items():
        meta = dict(meta)
        chosen = None
        for c in meta.get("candidates", []):
            if c in names:
                chosen = c
                break
        if chosen is None:
            # Prefix fallback (e.g. "Grok 4.7" vs slightly different labeling)
            for c in meta.get("candidates", []):
                hit = next((n for n in names if n == c or n.startswith(c + " ")), None)
                if hit:
                    chosen = c
                    break
        if chosen is not None:
            meta["display"] = chosen
        out[key] = meta
    return out


def dump_yaml(data: dict, path: Path) -> None:
    header = (
        "# AUTO-GENERATED by scripts/sync_models.py — do not hand-edit\n"
        f"# Source: {data.get('source_url')}\n"
        f"# Generated: {data.get('generated_at')}\n\n"
    )
    if yaml is not None:
        body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    else:
        body = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    path.write_text(header + body, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--url", default=None, help="Override docs URL")
    args = parser.parse_args()

    previous = args.out.read_text(encoding="utf-8") if args.out.exists() else None
    urls = (args.url,) if args.url else SOURCE_URLS

    last_err: Exception | None = None
    for url in urls:
        try:
            text = fetch_text(url)
            rows = parse_price_rows(text)
            if not rows:
                raise RuntimeError(f"No price rows parsed from {url}")
            cursor_pool, other_pool = split_pools(rows)
            logical = refresh_logical_displays(LOGICAL_SEED, rows)
            doc = {
                "version": 1,
                "source_url": url,
                "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "sync_status": "ok",
                "logical": logical,
                "cursor_models_pool": cursor_pool,
                "other_models_pool": other_pool,
                "plan_note": (
                    "Pro ($20/mo) includes Cursor Models pool + Other Models ~$20 API credit. "
                    "Auto/Router bills at routed model list price."
                ),
            }
            dump_yaml(doc, args.out)
            print(
                f"Wrote {args.out} ({len(rows)} rows; "
                f"cursor={len(cursor_pool)} other={len(other_pool)}) from {url}"
            )
            return 0
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"try failed for {url}: {exc}", file=sys.stderr)

    print(f"sync_models soft-fail: {last_err}", file=sys.stderr)
    if previous is not None:
        print("Kept previous models.generated.yaml", file=sys.stderr)
        return 1

    seed = {
        "version": 1,
        "source_url": urls[0],
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sync_status": "seed_after_fail",
        "logical": LOGICAL_SEED,
        "cursor_models_pool": [],
        "other_models_pool": [],
        "error": str(last_err),
    }
    dump_yaml(seed, args.out)
    print(f"Wrote seed fallback to {args.out}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
