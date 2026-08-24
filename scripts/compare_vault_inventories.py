#!/usr/bin/env python3
"""Compare active vault membership in RPC and Envio SQLite databases."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


def _active_vaults(path: Path, chain_id: int) -> dict[tuple[str, str], dict[str, Any]]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT chain_id, version, address, asset, deployment_block
        FROM vaults
        WHERE chain_id=? AND management='yearn' AND active=1
        """,
        (chain_id,),
    ).fetchall()
    conn.close()
    return {
        (row["version"], row["address"].lower()): dict(row)
        for row in rows
    }


def _sample(
    keys: set[tuple[str, str]],
    rows: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    return [rows[key] for key in sorted(keys)[:10]]


def compare(rpc_path: Path, envio_path: Path, chain_id: int) -> dict[str, Any]:
    rpc = _active_vaults(rpc_path, chain_id)
    envio = _active_vaults(envio_path, chain_id)
    rpc_keys, envio_keys = set(rpc), set(envio)
    return {
        "chain_id": chain_id,
        "rpc_database": str(rpc_path.resolve()),
        "envio_database": str(envio_path.resolve()),
        "rpc_vaults": len(rpc),
        "envio_vaults": len(envio),
        "rpc_by_version": dict(sorted(Counter(key[0] for key in rpc).items())),
        "envio_by_version": dict(sorted(Counter(key[0] for key in envio).items())),
        "shared": len(rpc_keys & envio_keys),
        "rpc_only": len(rpc_keys - envio_keys),
        "envio_only": len(envio_keys - rpc_keys),
        "rpc_only_sample": _sample(rpc_keys - envio_keys, rpc),
        "envio_only_sample": _sample(envio_keys - rpc_keys, envio),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rpc_db", type=Path)
    parser.add_argument("envio_db", type=Path)
    parser.add_argument("--chain-id", type=int, default=1)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--require-parity", action="store_true")
    args = parser.parse_args()

    result = compare(args.rpc_db, args.envio_db, args.chain_id)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered)
    print(rendered, end="")
    if args.require_parity and (result["rpc_only"] or result["envio_only"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
