from yearn_data.config import CHAINS
from yearn_data.pricing import (
    _aave_atoken_price,
    _curve_pool_from_registry,
    _exchange_rate_wrapped_price,
    price_unpriced_reports,
    price_unpriced_volume,
)
from yearn_data.storage import connect, init_db, seed_chains


def test_price_unpriced_reports_uses_defillama_primary_and_yprice_fallback(monkeypatch, tmp_path):
    conn = connect(tmp_path / "test.sqlite")
    init_db(conn)
    seed_chains(conn, CHAINS)
    conn.execute(
        """
        INSERT INTO strategy_reports (
            chain_id, version, vault_address, strategy_address, tx_hash, log_index,
            block_number, block_timestamp, asset, asset_decimals, gain_raw, loss_raw,
            net_raw, extra_json
        )
        VALUES (1, 'v3', '0x0000000000000000000000000000000000000001',
                '0x0000000000000000000000000000000000000003',
                '0xabc', 0, 10, 100, '0x0000000000000000000000000000000000000002',
                6, '1', '0', '1', '{}')
        """
    )
    conn.execute(
        """
        INSERT INTO prices (
            chain_id, token_address, timestamp, block_number, source, price_usd, status
        )
        VALUES (1, '0x0000000000000000000000000000000000000002', 100, 10, 'yprice', NULL, 'error')
        """
    )
    conn.commit()

    def fake_defillama_batch(requests_):
        return {
            (chain_id, token_address, timestamp): (None, "error", {"source": "defillama"})
            for chain_id, token_address, timestamp in requests_
        }

    def fake_yprice(chain_id, token_address, block_number):
        return 2.0, "ok", {"source": "yprice"}

    monkeypatch.setattr("yearn_data.pricing.fetch_defillama_prices_batch", fake_defillama_batch)
    monkeypatch.setattr("yearn_data.pricing.fetch_yprice_price", fake_yprice)
    count = price_unpriced_reports(conn, source="defillama", fallback="yprice")
    assert count == 2
    statuses = {
        row["source"]: row["status"]
        for row in conn.execute("SELECT source, status FROM prices").fetchall()
    }
    assert statuses == {"defillama": "error", "yprice": "ok"}


def test_price_unpriced_volume_uses_flow_tables(monkeypatch, tmp_path):
    conn = connect(tmp_path / "test.sqlite")
    init_db(conn)
    seed_chains(conn, CHAINS)
    conn.execute(
        """
        INSERT INTO vault_flows (
            chain_id, version, vault_address, direction, tx_hash, log_index,
            block_number, block_timestamp, asset, asset_decimals, assets_raw,
            shares_raw, decoded_json
        )
        VALUES (1, 'v3', '0x0000000000000000000000000000000000000001',
                'deposit', '0xabc', 0, 10, 100,
                '0x0000000000000000000000000000000000000002',
                6, '1000000', '1000000', '{}')
        """
    )
    conn.commit()

    def fake_defillama_batch(requests_):
        return {
            (chain_id, token_address, timestamp): (3.0, "ok", {"source": "defillama"})
            for chain_id, token_address, timestamp in requests_
        }

    monkeypatch.setattr("yearn_data.pricing.fetch_defillama_prices_batch", fake_defillama_batch)
    count = price_unpriced_volume(conn, source="defillama", fallback=None)
    assert count == 1
    row = conn.execute("SELECT price_usd, status FROM prices").fetchone()
    assert row["price_usd"] == 3.0
    assert row["status"] == "ok"


def test_price_unpriced_volume_can_retry_missing_with_polygon_stable_fallback(monkeypatch, tmp_path):
    conn = connect(tmp_path / "test.sqlite")
    init_db(conn)
    seed_chains(conn, CHAINS)
    usdt = "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"
    conn.execute(
        """
        INSERT INTO vault_flows (
            chain_id, version, vault_address, direction, tx_hash, log_index,
            block_number, block_timestamp, asset, asset_decimals, assets_raw,
            shares_raw, decoded_json
        )
        VALUES (137, 'v3', '0x0000000000000000000000000000000000000001',
                'deposit', '0xabc', 0, 10, 100, ?, 6, '1000000',
                '1000000', '{}')
        """,
        (usdt,),
    )
    conn.execute(
        """
        INSERT INTO prices (
            chain_id, token_address, timestamp, block_number, source, price_usd,
            status, raw_json
        )
        VALUES (137, ?, 100, 10, 'defillama', NULL, 'missing', '{}')
        """,
        (usdt,),
    )
    conn.commit()

    def fake_defillama_batch(requests_):
        return {
            (chain_id, token_address, timestamp): (
                1.0,
                "ok",
                {"source": "canonical_polygon_stable_fallback"},
            )
            for chain_id, token_address, timestamp in requests_
        }

    monkeypatch.setattr("yearn_data.pricing.fetch_defillama_prices_batch", fake_defillama_batch)

    count = price_unpriced_volume(
        conn,
        source="defillama",
        fallback=None,
        retry_missing=True,
        chain_ids={137},
    )

    assert count == 1
    row = conn.execute("SELECT price_usd, status, raw_json FROM prices").fetchone()
    assert row["price_usd"] == 1.0
    assert row["status"] == "ok"
    assert "canonical_polygon_stable_fallback" in row["raw_json"]


def test_price_unpriced_reports_retries_missing_with_v3_alias(monkeypatch, tmp_path):
    conn = connect(tmp_path / "test.sqlite")
    init_db(conn)
    seed_chains(conn, CHAINS)
    usdt = "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9"
    conn.execute(
        """
        INSERT INTO strategy_reports (
            chain_id, version, vault_address, strategy_address, tx_hash, log_index,
            block_number, block_timestamp, asset, asset_decimals, gain_raw, loss_raw,
            net_raw, extra_json
        )
        VALUES (42161, 'v3', '0x0000000000000000000000000000000000000001',
                '0x0000000000000000000000000000000000000003',
                '0xabc', 0, 10, 100, ?, 6, '1', '0', '1', '{}')
        """,
        (usdt,),
    )
    conn.execute(
        """
        INSERT INTO prices (
            chain_id, token_address, timestamp, block_number, source, price_usd,
            status, raw_json
        )
        VALUES (42161, ?, 100, 10, 'defillama', NULL, 'missing', '{}')
        """,
        (usdt,),
    )
    conn.commit()

    def fake_defillama_batch(requests_):
        return {
            (chain_id, token_address, timestamp): (None, "missing", {"source": "defillama"})
            for chain_id, token_address, timestamp in requests_
        }

    monkeypatch.setattr("yearn_data.pricing.fetch_defillama_prices_batch", fake_defillama_batch)
    count = price_unpriced_reports(
        conn,
        source="defillama",
        fallback=None,
        retry_missing=True,
        chain_ids={42161},
    )

    assert count == 1
    row = conn.execute("SELECT price_usd, status, raw_json FROM prices").fetchone()
    assert row["price_usd"] == 1.0
    assert row["status"] == "ok"
    assert "canonical_arbitrum_stable_fallback" in row["raw_json"]


def test_price_unpriced_reports_uses_curve_lp_fallback(monkeypatch, tmp_path):
    conn = connect(tmp_path / "test.sqlite")
    init_db(conn)
    seed_chains(conn, CHAINS)
    lp = "0x06325440D014e39736583c165C2963BA99fAf14E"
    conn.execute(
        """
        INSERT INTO strategy_reports (
            chain_id, version, vault_address, strategy_address, tx_hash, log_index,
            block_number, block_timestamp, asset, asset_decimals, gain_raw, loss_raw,
            net_raw, extra_json
        )
        VALUES (1, 'v2', '0x0000000000000000000000000000000000000001',
                '0x0000000000000000000000000000000000000003',
                '0xabc', 0, 10, 100, ?, 18, '1', '0', '1', '{}')
        """,
        (lp,),
    )
    conn.execute(
        """
        INSERT INTO prices (
            chain_id, token_address, timestamp, block_number, source, price_usd,
            status, raw_json
        )
        VALUES (1, ?, 100, 10, 'defillama', NULL, 'missing', '{}')
        """,
        (lp,),
    )
    conn.commit()

    def fake_defillama_batch(requests_):
        return {
            (chain_id, token_address, timestamp): (None, "missing", {"source": "defillama"})
            for chain_id, token_address, timestamp in requests_
        }

    def fake_curve(chain_id, token_address, timestamp, block_number):
        return 123.45, {"source": "curve_lp_balance_fallback"}

    monkeypatch.setattr("yearn_data.pricing.fetch_defillama_prices_batch", fake_defillama_batch)
    monkeypatch.setattr("yearn_data.pricing._curve_lp_price", fake_curve)
    count = price_unpriced_reports(conn, source="defillama", fallback=None, retry_missing=True, chain_ids={1})

    assert count == 1
    row = conn.execute("SELECT price_usd, status, raw_json FROM prices").fetchone()
    assert row["price_usd"] == 123.45
    assert row["status"] == "ok"
    assert "curve_lp_balance_fallback" in row["raw_json"]


def test_curve_pool_from_registry_resolves_lp_when_minter_is_missing(monkeypatch):
    registry = "0x00000000000000000000000000000000000000a1"
    pool = "0x00000000000000000000000000000000000000b2"
    lp = "0x00000000000000000000000000000000000000c3"

    _curve_pool_from_registry.cache_clear()

    def fake_call_address(chain_id, address, signature, block_number, args_hex=""):
        if signature == "get_address(uint256)" and args_hex == "0".rjust(64, "0"):
            return registry
        if signature == "get_pool_from_lp_token(address)" and address == registry:
            return pool
        return None

    monkeypatch.setattr("yearn_data.pricing._call_address", fake_call_address)

    assert _curve_pool_from_registry(1, lp, 100) == pool
    _curve_pool_from_registry.cache_clear()


def test_exchange_rate_wrapped_price_uses_underlying_value(monkeypatch):
    token = "0x00000000000000000000000000000000000000c0"
    underlying = "0x00000000000000000000000000000000000000d0"

    def fake_call_address(chain_id, address, signature, block_number, args_hex=""):
        if address == token and signature == "underlying()":
            return underlying
        return None

    def fake_call_uint256(chain_id, address, signature, block_number, args_hex=""):
        if address == token and signature == "exchangeRateStored()":
            return 2 * 10**26
        if signature == "decimals()" and address == token:
            return 8
        if signature == "decimals()" and address == underlying:
            return 18
        return None

    def fake_direct(chain_id, token_address, timestamp, block_number):
        assert token_address == underlying
        return 1.5, {"source": "underlying"}

    monkeypatch.setattr("yearn_data.pricing._call_address", fake_call_address)
    monkeypatch.setattr("yearn_data.pricing._call_uint256", fake_call_uint256)
    monkeypatch.setattr("yearn_data.pricing._direct_or_alias_price", fake_direct)

    price, payload = _exchange_rate_wrapped_price(1, token, 100, 10)

    assert price == 0.03
    assert payload["source"] == "exchange_rate_wrapper_fallback"


def test_aave_atoken_price_uses_underlying_value(monkeypatch):
    token = "0x00000000000000000000000000000000000000a0"
    underlying = "0x00000000000000000000000000000000000000d0"

    def fake_call_address(chain_id, address, signature, block_number, args_hex=""):
        if address == token and signature == "UNDERLYING_ASSET_ADDRESS()":
            return underlying
        return None

    def fake_direct(chain_id, token_address, timestamp, block_number):
        assert token_address == underlying
        return 1.25, {"source": "underlying"}

    monkeypatch.setattr("yearn_data.pricing._call_address", fake_call_address)
    monkeypatch.setattr("yearn_data.pricing._direct_or_alias_price", fake_direct)

    price, payload = _aave_atoken_price(1, token, 100, 10)

    assert price == 1.25
    assert payload["source"] == "aave_atoken_fallback"


def test_price_unpriced_reports_uses_crv_derivative_fallback(monkeypatch, tmp_path):
    conn = connect(tmp_path / "test.sqlite")
    init_db(conn)
    seed_chains(conn, CHAINS)
    ycrv = "0xFCc5c47bE19d06BF83eB04298b026F81069ff65b"
    conn.execute(
        """
        INSERT INTO strategy_reports (
            chain_id, version, vault_address, strategy_address, tx_hash, log_index,
            block_number, block_timestamp, asset, asset_decimals, gain_raw, loss_raw,
            net_raw, extra_json
        )
        VALUES (1, 'v2', '0x0000000000000000000000000000000000000001',
                '0x0000000000000000000000000000000000000003',
                '0xabc', 0, 10, 100, ?, 18, '1', '0', '1', '{}')
        """,
        (ycrv,),
    )
    conn.execute(
        """
        INSERT INTO prices (
            chain_id, token_address, timestamp, block_number, source, price_usd,
            status, raw_json
        )
        VALUES (1, ?, 100, 10, 'defillama', NULL, 'missing', '{}')
        """,
        (ycrv,),
    )
    conn.commit()

    def fake_defillama_batch(requests_):
        return {
            (chain_id, token_address, timestamp): (None, "missing", {"source": "defillama"})
            for chain_id, token_address, timestamp in requests_
        }

    def fake_crv_derivative(chain_id, token_address, timestamp, block_number):
        return 0.42, {"source": "curve_get_dy_fallback"}

    monkeypatch.setattr("yearn_data.pricing.fetch_defillama_prices_batch", fake_defillama_batch)
    monkeypatch.setattr("yearn_data.pricing._crv_derivative_price", fake_crv_derivative)

    count = price_unpriced_reports(conn, source="defillama", fallback=None, retry_missing=True, chain_ids={1})

    assert count == 1
    row = conn.execute("SELECT price_usd, status, raw_json FROM prices").fetchone()
    assert row["price_usd"] == 0.42
    assert row["status"] == "ok"
    assert "curve_get_dy_fallback" in row["raw_json"]
