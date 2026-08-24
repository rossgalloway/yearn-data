#!/usr/bin/env python3
"""Copy the baseline vault scope into an empty candidate benchmark database."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

VAULT_COLUMNS = (
    "chain_id",
    "version",
    "address",
    "source_address",
    "asset",
    "asset_symbol",
    "asset_decimals",
    "name",
    "api_version",
    "management",
    "protocol",
    "deployment_block",
    "active",
    "updated_at",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline_db", type=Path)
    parser.add_argument("candidate_db", type=Path)
    args = parser.parse_args()

    conn = sqlite3.connect(args.candidate_db)
    report_count = conn.execute("SELECT COUNT(*) FROM strategy_reports").fetchone()[0]
    vault_count = conn.execute("SELECT COUNT(*) FROM vaults").fetchone()[0]
    if report_count or vault_count:
        raise RuntimeError("candidate database must have empty vaults and strategy_reports tables")

    conn.execute("ATTACH DATABASE ? AS baseline", (str(args.baseline_db.resolve()),))
    columns = ", ".join(VAULT_COLUMNS)
    conn.execute(f"INSERT INTO vaults ({columns}) SELECT {columns} FROM baseline.vaults")
    conn.commit()
    copied = conn.execute("SELECT COUNT(*) FROM vaults").fetchone()[0]
    conn.close()
    print(f"copied {copied} baseline vault rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
