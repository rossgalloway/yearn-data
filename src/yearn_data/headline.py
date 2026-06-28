"""Redis headline publishers for analysis outputs."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .storage import from_json


LIFETIME_YIELD_HEADLINE_KEY = "lifetime_yield:headline"


def _decimal_text(value: Decimal | str | int | float) -> str:
    return format(Decimal(str(value)), "f")


def _iso_run_id(timestamp: int | None) -> str:
    if timestamp is None:
        return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def latest_lifetime_yield_anchor(conn, analysis_run_id: int | None = None) -> tuple[Decimal, str]:
    """Return the latest completed lifetime-yield net value and default run id."""

    params: tuple[Any, ...]
    if analysis_run_id is None:
        where = "r.name='lifetime-yield' AND r.status='complete'"
        params = ()
    else:
        where = "r.id=? AND r.name='lifetime-yield' AND r.status='complete'"
        params = (analysis_run_id,)

    row = conn.execute(
        f"""
        SELECT r.id, r.completed_at, r.started_at, o.row_json
        FROM analysis_runs r
        JOIN analysis_outputs o
          ON o.run_id = r.id
         AND o.name = 'total_yield_summary'
        WHERE {where}
        ORDER BY r.id DESC
        LIMIT 1
        """,
        params,
    ).fetchone()
    if row is None:
        if analysis_run_id is None:
            raise ValueError("no completed lifetime-yield analysis output found; run `yearn-data analyze lifetime-yield` first")
        raise ValueError(f"completed lifetime-yield analysis run {analysis_run_id} was not found")

    summary = from_json(row["row_json"])
    if "net_yield_usd" not in summary or summary["net_yield_usd"] is None:
        raise ValueError(f"lifetime-yield analysis run {row['id']} has no net_yield_usd")

    run_id = f"analysis-run-{row['id']}:{_iso_run_id(row['completed_at'] or row['started_at'])}"
    return Decimal(str(summary["net_yield_usd"])), run_id


def build_lifetime_yield_headline(
    net_yield_usd: Decimal | str | int | float,
    previous: dict[str, Any] | None,
    *,
    now_ms: int | None = None,
    run_id: str,
) -> dict[str, Any]:
    """Build the Redis payload while preserving monotonic timestamps and non-negative rate."""

    now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    new_value = Decimal(str(net_yield_usd))
    previous = previous or None
    if previous:
        prev_as_of_ms = int(previous["as_of_ms"])
        now_ms = max(now_ms, prev_as_of_ms)
        prev_value = Decimal(str(previous["net_yield_usd"]))
        dt_seconds = Decimal(now_ms - prev_as_of_ms) / Decimal(1000)
        if dt_seconds > 0:
            rate = max(0.0, float((new_value - prev_value) / dt_seconds))
        else:
            rate = 0.0
    else:
        prev_value = new_value
        prev_as_of_ms = now_ms
        rate = 0.0

    return {
        "net_yield_usd": new_value,
        "as_of_ms": now_ms,
        "rate_usd_per_sec": rate,
        "prev_net_yield_usd": prev_value,
        "prev_as_of_ms": prev_as_of_ms,
        "run_id": run_id,
    }


def lifetime_yield_headline_json(payload: dict[str, Any]) -> str:
    """Serialize the headline payload with Decimal values as JSON numbers, not strings."""

    fields = [
        f'"net_yield_usd": {_decimal_text(payload["net_yield_usd"])}',
        f'"as_of_ms": {int(payload["as_of_ms"])}',
        f'"rate_usd_per_sec": {float(payload["rate_usd_per_sec"])}',
        f'"prev_net_yield_usd": {_decimal_text(payload["prev_net_yield_usd"])}',
        f'"prev_as_of_ms": {int(payload["prev_as_of_ms"])}',
        f'"run_id": {json.dumps(str(payload["run_id"]))}',
    ]
    return "{" + ",".join(fields) + "}"


def parse_previous_headline(raw: bytes | str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def publish_lifetime_yield_headline(
    conn,
    *,
    redis_url: str | None = None,
    redis_client: Any | None = None,
    key: str = LIFETIME_YIELD_HEADLINE_KEY,
    ttl: int | None = None,
    analysis_run_id: int | None = None,
    run_id: str | None = None,
    now_ms: int | None = None,
    dry_run: bool = False,
) -> tuple[dict[str, Any], str]:
    """Publish or dry-run the latest lifetime-yield headline Redis blob."""

    net_yield_usd, default_run_id = latest_lifetime_yield_anchor(conn, analysis_run_id)
    run_id = run_id or default_run_id

    previous = None
    if not dry_run:
        if redis_client is None:
            if not redis_url:
                raise ValueError("redis_url is required unless dry_run=True or redis_client is provided")
            from redis import Redis

            redis_client = Redis.from_url(redis_url)
        previous = parse_previous_headline(redis_client.get(key))

    payload = build_lifetime_yield_headline(net_yield_usd, previous, now_ms=now_ms, run_id=run_id)
    payload_json = lifetime_yield_headline_json(payload)
    if not dry_run:
        kwargs = {"ex": ttl} if ttl else {}
        redis_client.set(key, payload_json, **kwargs)
    return payload, payload_json
