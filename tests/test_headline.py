import json
from decimal import Decimal

from yearn_data.analysis import create_analysis_run, complete_analysis_run, write_output
from yearn_data.headline import (
    LIFETIME_YIELD_HEADLINE_KEY,
    build_lifetime_yield_headline,
    latest_lifetime_yield_anchor,
    lifetime_yield_headline_json,
    publish_lifetime_yield_headline,
)
from yearn_data.storage import connect, init_db


class FakeRedis:
    def __init__(self, raw=None):
        self.raw = raw
        self.set_args = None
        self.set_kwargs = None

    def get(self, key):
        assert key == LIFETIME_YIELD_HEADLINE_KEY
        return self.raw

    def set(self, *args, **kwargs):
        self.set_args = args
        self.set_kwargs = kwargs
        return True


def _db_with_lifetime_yield(tmp_path, value="125.123456789"):
    conn = connect(tmp_path / "test.sqlite")
    init_db(conn)
    run_id = create_analysis_run(conn, "lifetime-yield")
    write_output(
        conn,
        run_id,
        "total_yield_summary",
        {"dimension": "all", "key": "all", "net_yield_usd": value},
    )
    conn.commit()
    complete_analysis_run(conn, run_id)
    return conn, run_id


def test_latest_lifetime_yield_anchor_reads_completed_summary(tmp_path):
    conn, run_id = _db_with_lifetime_yield(tmp_path)

    value, default_run_id = latest_lifetime_yield_anchor(conn)

    assert value == Decimal("125.123456789")
    assert default_run_id.startswith(f"analysis-run-{run_id}:")


def test_build_lifetime_yield_headline_computes_non_negative_rate():
    payload = build_lifetime_yield_headline(
        Decimal("125"),
        {"net_yield_usd": "100", "as_of_ms": 1_000},
        now_ms=11_000,
        run_id="run",
    )

    assert payload["prev_net_yield_usd"] == Decimal("100")
    assert payload["prev_as_of_ms"] == 1_000
    assert payload["rate_usd_per_sec"] == 2.5

    payload = build_lifetime_yield_headline(
        Decimal("90"),
        {"net_yield_usd": "100", "as_of_ms": 1_000},
        now_ms=11_000,
        run_id="run",
    )
    assert payload["rate_usd_per_sec"] == 0.0


def test_lifetime_yield_headline_json_keeps_decimal_values_numeric():
    payload = build_lifetime_yield_headline(Decimal("125.123456789"), None, now_ms=1_000, run_id="run")

    payload_json = lifetime_yield_headline_json(payload)

    assert '"net_yield_usd": 125.123456789' in payload_json
    assert '"prev_net_yield_usd": 125.123456789' in payload_json
    assert json.loads(payload_json)["net_yield_usd"] == 125.123456789


def test_publish_lifetime_yield_headline_sets_atomic_json_with_ttl(tmp_path):
    conn, _ = _db_with_lifetime_yield(tmp_path)
    redis = FakeRedis(raw=b'{"net_yield_usd":"100","as_of_ms":1000}')

    payload, payload_json = publish_lifetime_yield_headline(
        conn,
        redis_client=redis,
        ttl=3600,
        now_ms=11_000,
        run_id="run",
    )

    assert payload["rate_usd_per_sec"] == 2.5123456789
    assert redis.set_args == (LIFETIME_YIELD_HEADLINE_KEY, payload_json)
    assert redis.set_kwargs == {"ex": 3600}
    assert json.loads(payload_json)["run_id"] == "run"
