# Envio event benchmark

This benchmark compares the current RPC report indexer with Envio at one fixed block.
It deliberately does not test pricing or tokenized strategies.

## Fair comparison rules

1. Read Ethereum's latest fully processed block from Envio and record it in `manifest.json`.
2. Run main-branch RPC discovery once, with `--find-deployment`.
3. Run candidate Envio discovery at the same block. V2 excludes experimental
   events by default; V3 replays role-manager add/remove events.
4. Confirm both databases contain the same active vault addresses.
5. Run `index-events --chains eth --versions v2 v3 --to-block <block>` against each source.
6. Compare `(chain_id, tx_hash, log_index)` and every normalized accounting field with `scripts/compare_event_databases.py`.

Use `YEARN_DATA_EVENT_SOURCE=rpc` for the baseline and
`YEARN_DATA_EVENT_SOURCE=envio` for the candidate. Keep the database files outside
the repository because they can be large and may contain partial runs.

The core command sequence is:

```sh
YEARN_DATA_EVENT_SOURCE=rpc yearn-data --db /tmp/rpc.sqlite init-db
YEARN_DATA_EVENT_SOURCE=rpc yearn-data --db /tmp/rpc.sqlite discover --chains eth --find-deployment

YEARN_DATA_EVENT_SOURCE=envio yearn-data --db /tmp/envio.sqlite init-db
YEARN_DATA_EVENT_SOURCE=envio yearn-data --db /tmp/envio.sqlite \
  discover --chains eth --to-block <block>

python scripts/compare_vault_inventories.py /tmp/rpc.sqlite /tmp/envio.sqlite \
  --require-parity

YEARN_DATA_EVENT_SOURCE=rpc yearn-data --db /tmp/rpc.sqlite \
  index-events --chains eth --versions v2 v3 --to-block <block>
YEARN_DATA_EVENT_SOURCE=envio yearn-data --db /tmp/envio.sqlite \
  index-events --chains eth --versions v2 v3 --to-block <block>

python scripts/compare_event_databases.py /tmp/rpc.sqlite /tmp/envio.sqlite \
  --require-semantic-parity
```

Load the same `.env` file for every command. Record wall time and peak memory for
the two `index-events` commands with the same measurement tool.

## Current result

The first Ethereum run is recorded in `results/ethereum-25806604.json` and the HTML report.
The report import has full key and normalized-field parity. The corrected discovery
rules reproduce the RPC membership counts and addresses from the indexed lifecycle:
367 V2 production vaults, plus 37 V3 vaults active after 74 additions and 37 removals.
The live Envio discovery rerun remains pending until the role-manager removal PR is
deployed and the indexer has rebuilt its historical data.
