"""Offline contract tests for Envio ingestion adapters and cursors."""

from __future__ import annotations

from yearn_data import envio
from yearn_data.config import CHAINS
from yearn_data.indexing import insert_strategy_report, normalize_strategy_report
from yearn_data.storage import connect, init_db, seed_chains

STRATEGY = "0x" + "1" * 40
VAULT = "0x" + "2" * 40
ASSET = "0x" + "3" * 40
TX = "0x" + "ab" * 32


def _v3_report_node(*, block: int = 100, log_index: int = 7) -> dict[str, str | int]:
    return {
        "gain": "10",
        "loss": "3",
        "current_debt": "500",
        "protocol_fees": "1",
        "total_fees": "2",
        "total_refunds": "0",
        "strategy": STRATEGY,
        "vaultAddress": VAULT,
        "chainId": 1,
        "blockNumber": block,
        "blockTimestamp": 1_700_000_000,
        "transactionHash": TX,
        "logIndex": log_index,
    }


def _v2_report_node(*, block: int = 100, log_index: int = 7) -> dict[str, str | int]:
    return {
        "gain": "10",
        "loss": "3",
        "debtAdded": "20",
        "debtPaid": "5",
        "totalGain": "100",
        "totalLoss": "30",
        "totalDebt": "500",
        "debtRatio": "9000",
        "strategy": STRATEGY,
        "vaultAddress": VAULT,
        "chainId": 1,
        "blockNumber": block,
        "blockTimestamp": 1_700_000_000,
        "transactionHash": TX,
        "logIndex": log_index,
    }


def _db(tmp_path):
    conn = connect(tmp_path / "envio.sqlite")
    init_db(conn)
    seed_chains(conn, CHAINS)
    return conn


def _seed_vault(conn) -> None:
    conn.execute(
        """
        INSERT INTO vaults (
            chain_id, version, address, source_address, asset, asset_symbol,
            asset_decimals, name, api_version, deployment_block, updated_at
        ) VALUES (1, 'v3', ?, '0xsource', ?, 'USDC', 6, 'vault', '3.0.0', 42, 1)
        """,
        (VAULT, ASSET),
    )
    conn.commit()


def _seed_v2_vault(conn) -> None:
    conn.execute(
        """
        INSERT INTO vaults (
            chain_id, version, address, source_address, asset, asset_symbol,
            asset_decimals, name, api_version, deployment_block, updated_at
        ) VALUES (1, 'v2', ?, '0xsource', ?, 'USDC', 6, 'vault', '0.4.3', 42, 1)
        """,
        (VAULT, ASSET),
    )
    conn.commit()


def test_report_nodes_match_existing_normalizer():
    v3 = _v3_report_node()
    assert envio.normalize_strategy_report(
        1, "v3", VAULT, ASSET, 6, envio._log(v3), int(v3["blockTimestamp"]), envio._v3_report_args(v3)
    ) == normalize_strategy_report(
        1,
        "v3",
        VAULT,
        ASSET,
        6,
        {"transactionHash": TX, "logIndex": 7, "blockNumber": 100},
        1_700_000_000,
        {"strategy": STRATEGY, "gain": 10, "loss": 3, "current_debt": 500, "protocol_fees": 1, "total_fees": 2, "total_refunds": 0},
    )

    v2 = _v2_report_node()
    assert envio.normalize_strategy_report(
        1, "v2", VAULT, ASSET, 6, envio._log(v2), int(v2["blockTimestamp"]), envio._v2_report_args(v2)
    ) == normalize_strategy_report(
        1,
        "v2",
        VAULT,
        ASSET,
        6,
        {"transactionHash": TX, "logIndex": 7, "blockNumber": 100},
        1_700_000_000,
        {"strategy": STRATEGY, "gain": 10, "loss": 3, "debtAdded": 20, "debtPaid": 5, "totalGain": 100, "totalLoss": 30, "totalDebt": 500, "debtRatio": 9000},
    )


def test_pull_window_paginates_a_stable_block_log_cursor(monkeypatch):
    first = _v3_report_node(block=10, log_index=1)
    second = _v3_report_node(block=10, log_index=2)
    calls = []

    def fake_gql(query, variables, timeout=120):
        calls.append(variables)
        return {"StrategyReported": [first, second] if len(calls) == 1 else []}

    monkeypatch.setattr(envio, "_gql", fake_gql)
    assert envio._pull_window("StrategyReported", envio.V3_REPORT_FIELDS, 1, 10, 10, page_size=2) == [first, second]
    assert calls == [{"lb": 9, "li": -1, "n": 2}, {"lb": 10, "li": 2, "n": 2}]


def test_import_reports_sets_a_source_cursor_and_is_idempotent(tmp_path, monkeypatch):
    conn = _db(tmp_path)
    _seed_vault(conn)
    v3 = _v3_report_node()

    monkeypatch.setattr(envio, "_pull_window", lambda *args, **kwargs: [v3])
    monkeypatch.setattr(envio, "_window_blocks", lambda: 1_000_000)
    assert envio.import_reports_from_envio(conn, ["eth"], versions=["v3"], to_block=100) == 1
    row = conn.execute("SELECT asset, asset_decimals, gain_raw, net_raw FROM strategy_reports").fetchone()
    assert tuple(row) == (ASSET, 6, "10", "7")
    assert envio._get_envio_cursor(conn, 1, "StrategyReported") == 100

    monkeypatch.setattr(envio, "_pull_window", lambda *args, **kwargs: [])
    assert envio.import_reports_from_envio(conn, ["eth"], versions=["v3"], to_block=100) == 0



def test_v2_fee_import_uses_envio_transfers_and_batched_archive_pps(tmp_path, monkeypatch):
    conn = _db(tmp_path)
    _seed_v2_vault(conn)
    report = _v2_report_node(block=100, log_index=7)
    insert_strategy_report(
        conn,
        normalize_strategy_report(
            1,
            "v2",
            VAULT,
            ASSET,
            6,
            envio._log(report),
            int(report["blockTimestamp"]),
            envio._v2_report_args(report),
        ),
    )
    conn.commit()
    recipient = "0x" + "4" * 40
    transfers = [
        {
            "vaultAddress": VAULT,
            "sender": "0x" + "0" * 40,
            "receiver": VAULT,
            "value": "2000000",
            "chainId": 1,
            "blockNumber": 100,
            "blockTimestamp": 1_700_000_000,
            "transactionHash": TX,
            "logIndex": 8,
        },
        {
            "vaultAddress": VAULT,
            "sender": VAULT,
            "receiver": recipient,
            "value": "2000000",
            "chainId": 1,
            "blockNumber": 100,
            "blockTimestamp": 1_700_000_000,
            "transactionHash": TX,
            "logIndex": 9,
        },
    ]
    monkeypatch.setattr(envio, "_pull_v2_fee_transfers", lambda tx_hashes: transfers)
    monkeypatch.setattr(
        envio,
        "vault_metadata_from_kong",
        lambda _chain_id, addresses: {
            VAULT: {
                "asset": ASSET,
                "asset_symbol": "USDC",
                "asset_decimals": 6,
                "share_decimals": 6,
                "name": "vault",
                "api_version": "0.4.3",
            }
        },
    )
    pps_calls = []

    def fake_pps(conn, chain, vaults, logs, share_decimals_by_address=None):
        pps_calls.append((chain, logs, share_decimals_by_address))
        return {(VAULT, 100): (1_500_000, 6)}

    monkeypatch.setattr(envio, "_cached_vault_share_prices_many", fake_pps)

    assert envio.index_v2_fee_mints_from_envio(conn) == 1
    event = conn.execute(
        "SELECT source, recipient, fee_raw, shares_raw FROM vault_fee_events"
    ).fetchone()
    assert tuple(event) == ("v2_harvest_fee_transfer", recipient, "3000000", "2000000")
    assert pps_calls == [
        (
            "eth",
            [{"address": VAULT, "blockNumber": 100}],
            {VAULT: 6},
        )
    ]
    assert envio.index_v2_fee_mints_from_envio(conn) == 0




def test_cli_index_fees_uses_envio_by_default(tmp_path, monkeypatch):
    from yearn_data import cli

    conn = _db(tmp_path)
    calls: list[tuple] = []
    monkeypatch.delenv("YEARN_DATA_EVENT_SOURCE", raising=False)
    monkeypatch.setattr(cli, "open_db", lambda _path: conn)
    monkeypatch.setattr(
        cli,
        "index_v2_fee_mints_from_envio",
        lambda *args, **kwargs: calls.append((args, kwargs)) or 1,
    )
    monkeypatch.setattr(
        cli,
        "index_v2_fee_mints_from_reports",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected RPC receipt path")),
    )

    assert cli.main(["--db", str(tmp_path / "unused.sqlite"), "index-fees", "--chains", "eth"]) == 0
    assert len(calls) == 1

def test_report_import_skips_vaults_missing_from_yearn_metadata(tmp_path, monkeypatch):
    conn = _db(tmp_path)
    monkeypatch.setattr(envio, "_pull_window", lambda *args, **kwargs: [_v3_report_node()])
    monkeypatch.setattr(envio, "_window_blocks", lambda: 1_000_000)

    assert envio.import_reports_from_envio(conn, ["eth"], versions=["v3"], to_block=100) == 0
    assert conn.execute("SELECT COUNT(*) FROM strategy_reports").fetchone()[0] == 0
def test_envio_discovery_reuses_cached_metadata_and_preserves_rpc_facts(tmp_path, monkeypatch):
    conn = _db(tmp_path)
    _seed_vault(conn)
    monkeypatch.setattr(
        envio,
        "_distinct_vault_addresses",
        lambda _chain_id, entities: {VAULT} if entities == envio.V3_DISCOVERY_ENTITIES else {"0x" + "4" * 40},
    )
    monkeypatch.setattr(envio, "vault_metadata_from_kong", lambda *args: (_ for _ in ()).throw(AssertionError("unexpected Kong query")))

    assert envio.discover_from_envio(conn, ["eth"], skip_v2=True) == 1
    row = conn.execute("SELECT source_address, deployment_block, asset, management FROM vaults WHERE address=?", (VAULT,)).fetchone()
    assert tuple(row) == ("0xsource", 42, ASSET, "yearn")


def test_envio_discovery_resolves_missing_asset_decimals_from_kong(tmp_path, monkeypatch):
    conn = _db(tmp_path)
    monkeypatch.setattr(
        envio,
        "_distinct_vault_addresses",
        lambda _chain_id, entities: {VAULT} if entities == envio.V3_DISCOVERY_ENTITIES else set(),
    )
    monkeypatch.setattr(
        envio,
        "vault_metadata_from_kong",
        lambda chain_id, addresses: {
            VAULT: {
                "asset": ASSET,
                "asset_symbol": "USDC",
                "asset_decimals": 6,
                "name": "vault",
                "api_version": "3.0.0",
            }
        },
    )

    assert envio.discover_from_envio(conn, ["eth"], skip_v2=True) == 1
    row = conn.execute("SELECT asset, asset_symbol, asset_decimals FROM vaults WHERE address=?", (VAULT,)).fetchone()
    assert tuple(row) == (ASSET, "USDC", 6)



def test_cli_run_lifetime_yield_uses_envio_by_default(tmp_path, monkeypatch):
    from yearn_data import cli

    conn = _db(tmp_path)
    calls: list[str] = []
    monkeypatch.delenv("YEARN_DATA_EVENT_SOURCE", raising=False)
    monkeypatch.setattr(cli, "open_db", lambda _path: conn)
    monkeypatch.setattr(
        cli,
        "discover_from_envio",
        lambda *args, **kwargs: calls.append("discover") or 1,
    )
    monkeypatch.setattr(
        cli,
        "import_reports_from_envio",
        lambda *args, **kwargs: calls.append("reports") or 2,
    )
    monkeypatch.setattr(
        cli,
        "price_unpriced_reports",
        lambda *args, **kwargs: calls.append("price") or 3,
    )
    monkeypatch.setattr(
        cli,
        "_run_analysis",
        lambda *args, **kwargs: calls.append("analyze") or 4,
    )
    monkeypatch.setattr(cli, "export_analysis", lambda *args, **kwargs: calls.append("export") or [])

    assert cli.main(["--db", str(tmp_path / "unused.sqlite"), "run", "lifetime-yield", "--chains", "eth", "--to-block", "100"]) == 0
    assert calls == ["discover", "reports", "price", "analyze", "export"]