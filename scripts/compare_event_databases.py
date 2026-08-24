#!/usr/bin/env python3
"""Compare normalized strategy reports from RPC and Envio SQLite databases."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

KEY_FIELDS = ("chain_id", "tx_hash", "log_index")
SEMANTIC_FIELDS = (
    "version",
    "vault_address",
    "strategy_address",
    "block_number",
    "block_timestamp",
    "asset",
    "asset_decimals",
    "gain_raw",
    "loss_raw",
    "net_raw",
    "current_debt_raw",
    "protocol_fees_raw",
    "total_fees_raw",
    "total_refunds_raw",
)


def _rows(path: Path) -> dict[tuple[Any, ...], dict[str, Any]]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM strategy_reports").fetchall()
    conn.close()
    return {tuple(row[field] for field in KEY_FIELDS): dict(row) for row in rows}


def _sample(keys: set[tuple[Any, ...]], rows: dict[tuple[Any, ...], dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {field: rows[key][field] for field in (*KEY_FIELDS, "version", "vault_address", "block_number")}
        for key in sorted(keys)[:10]
    ]


def compare(rpc_path: Path, envio_path: Path) -> dict[str, Any]:
    rpc = _rows(rpc_path)
    envio = _rows(envio_path)
    rpc_keys, envio_keys = set(rpc), set(envio)
    shared = rpc_keys & envio_keys
    changed_fields = Counter()
    changed_keys: set[tuple[Any, ...]] = set()
    raw_json_changes = 0
    for key in shared:
        for field in SEMANTIC_FIELDS:
            if rpc[key][field] != envio[key][field]:
                changed_fields[field] += 1
                changed_keys.add(key)
        raw_json_changes += rpc[key]["extra_json"] != envio[key]["extra_json"]

    return {
        "rpc_database": str(rpc_path.resolve()),
        "envio_database": str(envio_path.resolve()),
        "rpc_reports": len(rpc),
        "envio_reports": len(envio),
        "rpc_by_version": dict(sorted(Counter(row["version"] for row in rpc.values()).items())),
        "envio_by_version": dict(sorted(Counter(row["version"] for row in envio.values()).items())),
        "shared_keys": len(shared),
        "rpc_only": len(rpc_keys - envio_keys),
        "envio_only": len(envio_keys - rpc_keys),
        "semantic_rows_changed": len(changed_keys),
        "semantic_field_changes": dict(sorted(changed_fields.items())),
        "raw_extra_json_changes": raw_json_changes,
        "rpc_only_sample": _sample(rpc_keys - envio_keys, rpc),
        "envio_only_sample": _sample(envio_keys - rpc_keys, envio),
        "semantic_change_sample": _sample(changed_keys, envio),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rpc_db", type=Path)
    parser.add_argument("envio_db", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--require-semantic-parity", action="store_true")
    args = parser.parse_args()
    result = compare(args.rpc_db, args.envio_db)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered)
    print(rendered, end="")
    if args.require_semantic_parity and any(
        result[field] for field in ("rpc_only", "envio_only", "semantic_rows_changed")
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
