"""Vault discovery for reusable index jobs."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace

from hexbytes import HexBytes
import requests
from web3 import Web3

from .abis import ROLE_MANAGER_ABI, V2_REGISTRY_ABI, V3_VAULT_FACTORY_NEW_VAULT_EVENT
from .chains import find_contract_creation_block, latest_block, web3_for
from .config import CHAINS, V2_ETH_REGISTRIES, V3_ROLE_MANAGERS, get_etherscan_api_key
from .contracts import checksum, contract, vault_metadata, vault_metadata_many
from .events import decode_event, event_topic
from .multicall import aggregate3_raw, decode_first, multicall_available


@dataclass(frozen=True)
class VaultRecord:
    chain_id: int
    version: str
    address: str
    source_address: str
    asset: str | None
    asset_symbol: str | None
    asset_decimals: int | None
    name: str | None
    api_version: str | None
    deployment_block: int | None
    management: str = "yearn"
    protocol: str | None = None


def discover_v3_vault_addresses(chain: str) -> list[str]:
    cfg = CHAINS[chain]
    manager = V3_ROLE_MANAGERS[cfg.chain_id]
    if manager == "0x0000000000000000000000000000000000000000":
        return []
    c = contract(chain, manager, ROLE_MANAGER_ABI)
    return [checksum(v) for v in c.functions.getAllVaults().call()]


V3_VAULT_FACTORIES = (
    "0x310aC28ACF5E514abDbFF9Ab25e21f1bfe22bcAC",  # 3.1.0
    "0x770D0d1Fb036483Ed4AbB6d53c1C88fb277D812F",  # 3.0.4
    "0x5577EdcB8A856582297CdBbB07055E6a6E38eb5f",  # 3.0.3
    "0x444045c5C13C246e117eD36437303cac8E250aB0",  # 3.0.2
    "0xE9E8C89c8Fc7E8b8F23425688eb68987231178e5",  # 3.0.1
)

V3_FACTORY_START_BLOCKS = {
    "eth": 17_000_000,
    "polygon": 45_000_000,
    "base": 0,
    "arb": 100_000_000,
    "kat": 0,
}

V3_FACTORY_DEPLOYMENT_BLOCKS = {
    "polygon": {
        "0x310aC28ACF5E514abDbFF9Ab25e21f1bfe22bcAC": 88_795_322,
        "0x770D0d1Fb036483Ed4AbB6d53c1C88fb277D812F": 63_721_181,
        "0x5577EdcB8A856582297CdBbB07055E6a6E38eb5f": 62_228_366,
        "0x444045c5C13C246e117eD36437303cac8E250aB0": 54_308_118,
        "0xE9E8C89c8Fc7E8b8F23425688eb68987231178e5": 48_907_735,
    },
    "base": {
        "0x310aC28ACF5E514abDbFF9Ab25e21f1bfe22bcAC": 47_554_109,
        "0x770D0d1Fb036483Ed4AbB6d53c1C88fb277D812F": 21_802_552,
        "0x5577EdcB8A856582297CdBbB07055E6a6E38eb5f": 20_207_449,
        "0x444045c5C13C246e117eD36437303cac8E250aB0": 12_295_872,
        "0xE9E8C89c8Fc7E8b8F23425688eb68987231178e5": 12_295_552,
    },
    "arb": {
        "0x310aC28ACF5E514abDbFF9Ab25e21f1bfe22bcAC": 475_224_753,
        "0x770D0d1Fb036483Ed4AbB6d53c1C88fb277D812F": 269_623_414,
        "0x5577EdcB8A856582297CdBbB07055E6a6E38eb5f": 256_920_915,
        "0x444045c5C13C246e117eD36437303cac8E250aB0": 187_480_878,
        "0xE9E8C89c8Fc7E8b8F23425688eb68987231178e5": 142_038_391,
    },
    "kat": {
        "0x310aC28ACF5E514abDbFF9Ab25e21f1bfe22bcAC": 35_157_654,
        "0x770D0d1Fb036483Ed4AbB6d53c1C88fb277D812F": 2_236_950,
    },
}


def discover_v3_factory_vault_addresses(chain: str, find_deployment: bool = False) -> dict[tuple[str, str], int]:
    w3 = web3_for(chain)
    topic = event_topic(V3_VAULT_FACTORY_NEW_VAULT_EVENT)
    start_block = V3_FACTORY_START_BLOCKS.get(chain, 0)
    if find_deployment:
        starts = []
        for factory in V3_VAULT_FACTORIES:
            try:
                factory_address = checksum(factory)
                if not w3.eth.get_code(factory_address):
                    continue
                starts.append(find_contract_creation_block(chain, factory_address))
            except Exception:
                continue
        if starts:
            start_block = min(starts)
    rows: dict[tuple[str, str], int] = {}
    for factory in V3_VAULT_FACTORIES:
        factory_address = checksum(factory)
        try:
            if not w3.eth.get_code(factory_address):
                continue
            factory_start = V3_FACTORY_DEPLOYMENT_BLOCKS.get(chain, {}).get(factory_address, start_block)
            logs = _get_logs_chunked(
                chain,
                {
                    "fromBlock": factory_start,
                    "toBlock": latest_block(chain),
                    "address": factory_address,
                    "topics": [topic],
                },
                chunk_size=1_000_000,
            )
        except Exception:
            continue
        for log in logs:
            _, args = decode_event(chain, [V3_VAULT_FACTORY_NEW_VAULT_EVENT], log)
            vault = args.get("vault_address")
            if not vault:
                continue
            key = (factory_address, checksum(vault))
            rows[key] = min(int(log["blockNumber"]), rows.get(key, int(log["blockNumber"])))
    return rows


def classify_non_yearn_protocol(record: VaultRecord) -> str:
    name = str(record.name or "").lower()
    symbol = str(record.asset_symbol or "").lower()
    text = " ".join(str(value or "").lower() for value in (record.name, record.asset_symbol, record.address, record.asset))
    if "sturdy" in text:
        return "sturdy-finance"
    if "term" in text:
        return "term-finance"
    if symbol == "cusd" or symbol.startswith("cusd") or name.startswith("cap ") or " cap " in f" {name} ":
        return "cap"
    if "scrvusd" in text or "savings crvusd" in name:
        return "curve-scrvusd"
    return "unknown"


def discover_v2_vault_addresses() -> list[tuple[str, str]]:
    """Return `(registry, vault)` rows for Ethereum V2 registries."""
    if multicall_available("eth"):
        return discover_v2_vault_addresses_multicall()
    return discover_v2_vault_addresses_sequential()


def discover_v2_vault_addresses_multicall() -> list[tuple[str, str]]:
    """Return `(registry, vault)` rows for Ethereum V2 registries using Multicall3."""
    rows: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for registry in V2_ETH_REGISTRIES:
        registry_address = checksum(registry)
        c = contract("eth", registry_address, V2_REGISTRY_ABI)
        token_count = int(c.functions.numTokens().call())
        token_calls = [
            (registry_address, c.functions.tokens(i)._encode_transaction_data())
            for i in range(token_count)
        ]
        token_results = aggregate3_raw("eth", token_calls)
        tokens = [
            checksum(token)
            for token in (decode_first("address", result) for result in token_results)
            if token
        ]
        num_vault_calls = [
            (registry_address, c.functions.numVaults(token)._encode_transaction_data())
            for token in tokens
        ]
        num_vault_results = aggregate3_raw("eth", num_vault_calls)
        vault_calls = []
        for token, result in zip(tokens, num_vault_results, strict=False):
            count = decode_first("uint256", result)
            for vault_idx in range(int(count or 0)):
                vault_calls.append((token, vault_idx, c.functions.vaults(token, vault_idx)._encode_transaction_data()))
        vault_results = aggregate3_raw("eth", [(registry_address, call_data) for _, _, call_data in vault_calls])
        for (token, vault_idx, _), result in zip(vault_calls, vault_results, strict=False):
            _ = token, vault_idx
            vault = decode_first("address", result)
            if not vault:
                continue
            key = (registry_address, checksum(vault))
            if key not in seen:
                seen.add(key)
                rows.append(key)
    return rows


def discover_v2_vault_addresses_sequential() -> list[tuple[str, str]]:
    """Return `(registry, vault)` rows for Ethereum V2 registries without Multicall3."""
    rows: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for registry in V2_ETH_REGISTRIES:
        c = contract("eth", registry, V2_REGISTRY_ABI)
        for i in range(int(c.functions.numTokens().call())):
            token = c.functions.tokens(i).call()
            for j in range(int(c.functions.numVaults(token).call())):
                vault = checksum(c.functions.vaults(token, j).call())
                key = (checksum(registry), vault)
                if key not in seen:
                    seen.add(key)
                    rows.append(key)
    return rows


def build_vault_record(chain: str, version: str, address: str, source_address: str, find_deployment: bool) -> VaultRecord:
    cfg = CHAINS[chain]
    metadata = vault_metadata(chain, address)
    deployment_block = None
    if find_deployment:
        deployment_block = find_contract_creation_block(chain, address)
    return VaultRecord(
        chain_id=cfg.chain_id,
        version=version,
        address=Web3.to_checksum_address(address),
        source_address=Web3.to_checksum_address(source_address),
        asset=metadata["asset"],
        asset_symbol=metadata["asset_symbol"],
        asset_decimals=metadata["asset_decimals"],
        name=metadata["name"],
        api_version=metadata["api_version"],
        deployment_block=deployment_block,
        management="yearn",
        protocol=None,
    )


def build_vault_records(
    chain: str,
    version: str,
    addresses: list[str],
    source_address: str,
    find_deployment: bool,
) -> list[VaultRecord]:
    cfg = CHAINS[chain]
    metadata_by_address = vault_metadata_many(chain, addresses)
    records: list[VaultRecord] = []
    for address in addresses:
        normalized = Web3.to_checksum_address(address)
        metadata = metadata_by_address.get(normalized) or vault_metadata(chain, normalized)
        deployment_block = None
        if find_deployment:
            deployment_block = find_contract_creation_block(chain, normalized)
        records.append(
            VaultRecord(
                chain_id=cfg.chain_id,
                version=version,
                address=normalized,
                source_address=Web3.to_checksum_address(source_address),
                asset=metadata["asset"],
                asset_symbol=metadata["asset_symbol"],
                asset_decimals=metadata["asset_decimals"],
                name=metadata["name"],
                api_version=metadata["api_version"],
                deployment_block=deployment_block,
                management="yearn",
                protocol=None,
            )
        )
    return records


def discover_v3_factory_vault_records(chain: str, find_deployment: bool = False) -> list[VaultRecord]:
    cfg = CHAINS[chain]
    factory_vaults = discover_v3_factory_vault_addresses(chain, find_deployment=find_deployment)
    if not factory_vaults:
        return []
    yearn_vaults = set(discover_v3_vault_addresses(chain))
    records: list[VaultRecord] = []
    by_factory: dict[str, list[tuple[str, int]]] = {}
    for (factory, vault), deployment_block in factory_vaults.items():
        if vault in yearn_vaults:
            continue
        by_factory.setdefault(factory, []).append((vault, deployment_block))
    for factory, rows in by_factory.items():
        addresses = [address for address, _ in rows]
        deployment_by_address = {address: deployment_block for address, deployment_block in rows}
        metadata_by_address = vault_metadata_many(chain, addresses)
        for address in addresses:
            metadata = metadata_by_address.get(address) or vault_metadata(chain, address)
            record = VaultRecord(
                chain_id=cfg.chain_id,
                version="v3",
                address=address,
                source_address=factory,
                asset=metadata["asset"],
                asset_symbol=metadata["asset_symbol"],
                asset_decimals=metadata["asset_decimals"],
                name=metadata["name"],
                api_version=metadata["api_version"],
                management="non_yearn",
                protocol=None,
                deployment_block=deployment_by_address.get(address),
            )
            records.append(replace(record, protocol=classify_non_yearn_protocol(record)))
    return records


def _get_logs_chunked(chain: str, params: dict, chunk_size: int = 100_000) -> list[dict]:
    w3 = web3_for(chain)
    start = int(params["fromBlock"])
    end = int(params["toBlock"])
    logs: list[dict] = []
    current = start
    while current <= end:
        chunk_end = min(current + chunk_size - 1, end)
        logs.extend(w3.eth.get_logs(dict(params, fromBlock=current, toBlock=chunk_end)))
        current = chunk_end + 1
    return logs


def _etherscan_v2_registry_logs(registry: str, event_abis: list[dict]) -> list[dict] | None:
    api_key = get_etherscan_api_key()
    if not api_key:
        return None
    logs: list[dict] = []
    for event_abi in event_abis:
        response = requests.get(
            "https://api.etherscan.io/v2/api",
            params={
                "chainid": "1",
                "module": "logs",
                "action": "getLogs",
                "fromBlock": "0",
                "toBlock": "latest",
                "address": checksum(registry),
                "topic0": event_topic(event_abi),
                "apikey": api_key,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        result = payload.get("result")
        if payload.get("status") == "0" and result == "No records found":
            continue
        if not isinstance(result, list):
            return None
        for item in result:
            transaction_index = item.get("transactionIndex")
            logs.append(
                {
                    "address": checksum(item["address"]),
                    "topics": [HexBytes(topic) for topic in item["topics"]],
                    "data": HexBytes(item["data"]),
                    "blockNumber": int(item["blockNumber"], 16),
                    "transactionHash": HexBytes(item["transactionHash"]),
                    "logIndex": int(item["logIndex"], 16),
                    "transactionIndex": int(transaction_index, 16) if transaction_index and transaction_index != "0x" else 0,
                    "blockHash": HexBytes(item["blockHash"]),
                }
            )
    return sorted(logs, key=lambda log: (int(log["blockNumber"]), int(log["logIndex"])))


def discover_v2_vault_records(find_deployment: bool) -> list[VaultRecord]:
    event_abis = [abi for abi in V2_REGISTRY_ABI if abi.get("type") == "event" and abi.get("name") == "NewVault"]
    topics = [event_topic(abi) for abi in event_abis]
    deployment_by_key: dict[tuple[str, str], int] = {}
    by_registry: dict[str, list[str]] = {}
    for registry in V2_ETH_REGISTRIES:
        registry_address = checksum(registry)
        logs = _etherscan_v2_registry_logs(registry_address, event_abis)
        if logs is None:
            start = find_contract_creation_block("eth", registry_address) if find_deployment else 0
            logs = _get_logs_chunked(
                "eth",
                {
                    "fromBlock": start,
                    "toBlock": latest_block("eth"),
                    "address": registry_address,
                    "topics": [topics],
                },
            )
        for log in logs:
            _, args = decode_event("eth", event_abis, log)
            vault = args.get("vault")
            if not vault:
                continue
            normalized = checksum(vault)
            key = (registry_address, normalized)
            deployment_by_key[key] = min(int(log["blockNumber"]), deployment_by_key.get(key, int(log["blockNumber"])))
            by_registry.setdefault(registry_address, []).append(normalized)

    if not deployment_by_key:
        for registry, vault in discover_v2_vault_addresses():
            by_registry.setdefault(registry, []).append(vault)

    records: list[VaultRecord] = []
    cfg = CHAINS["eth"]
    for registry, vaults in by_registry.items():
        unique_vaults = sorted(set(vaults))
        metadata_by_address = vault_metadata_many("eth", unique_vaults)
        for address in unique_vaults:
            metadata = metadata_by_address.get(address) or vault_metadata("eth", address)
            deployment_block = deployment_by_key.get((registry, address))
            if find_deployment and deployment_block is None:
                deployment_block = find_contract_creation_block("eth", address)
            records.append(
                VaultRecord(
                    chain_id=cfg.chain_id,
                    version="v2",
                    address=address,
                    source_address=registry,
                    asset=metadata["asset"],
                    asset_symbol=metadata["asset_symbol"],
                    asset_decimals=metadata["asset_decimals"],
                    name=metadata["name"],
                    api_version=metadata["api_version"],
                    deployment_block=deployment_block,
                )
            )
    return records


def upsert_vaults(conn, vaults: list[VaultRecord]) -> int:
    now = int(time.time())
    rows = [
        (
            v.chain_id,
            v.version,
            v.address,
            v.source_address,
            v.asset,
            v.asset_symbol,
            v.asset_decimals,
            v.name,
            v.api_version,
            v.deployment_block,
            v.management,
            v.protocol,
            now,
        )
        for v in vaults
    ]
    cur = conn.executemany(
        """
        INSERT INTO vaults (
            chain_id, version, address, source_address, asset, asset_symbol,
            asset_decimals, name, api_version, deployment_block, management,
            protocol, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chain_id, address) DO UPDATE SET
            version=excluded.version,
            source_address=excluded.source_address,
            asset=excluded.asset,
            asset_symbol=excluded.asset_symbol,
            asset_decimals=excluded.asset_decimals,
            name=excluded.name,
            api_version=excluded.api_version,
            deployment_block=COALESCE(excluded.deployment_block, vaults.deployment_block),
            management=excluded.management,
            protocol=excluded.protocol,
            updated_at=excluded.updated_at
        """,
        rows,
    )
    conn.commit()
    return cur.rowcount


def discover(
    conn,
    chains: list[str],
    find_deployment: bool = False,
    include_non_yearn: bool = False,
    skip_v2: bool = False,
) -> int:
    records: list[VaultRecord] = []
    for chain in chains:
        if chain in V3_ROLE_MANAGERS_BY_KEY:
            source = V3_ROLE_MANAGERS[CHAINS[chain].chain_id]
            vaults = discover_v3_vault_addresses(chain)
            records.extend(build_vault_records(chain, "v3", vaults, source, find_deployment))
            if include_non_yearn:
                records.extend(discover_v3_factory_vault_records(chain, find_deployment=find_deployment))
    if "eth" in chains and not skip_v2:
        records.extend(discover_v2_vault_records(find_deployment))
    return upsert_vaults(conn, records)


V3_ROLE_MANAGERS_BY_KEY = {cfg.key: V3_ROLE_MANAGERS[cfg.chain_id] for cfg in CHAINS.values() if cfg.chain_id in V3_ROLE_MANAGERS}
