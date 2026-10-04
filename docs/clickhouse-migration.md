# ClickHouse migration — duplicate group rows fix

## Why

Two bugs affected the ClickHouse storage:

1. **`trades_group` showed every closed trade twice** (once `status='open'`,
   once `status='close'`). `assign_groups` inserts a new "close" row for a
   trade instead of updating its existing "open" row, and
   `ReplacingMergeTree` only collapses rows with the same sorting key during
   *background merges, at an unpredictable time*. Nothing forced a merge or
   read with `FINAL`, so both rows stayed visible — and without a version
   column even a merge could keep the wrong one.
2. **`pair_name` was missing from the `ORDER BY`** of both tables: one
   transaction that trades two pairs (same hash + block timestamp) produced
   rows with identical sorting keys, so one of them was silently dropped at
   merge time (data loss).

The new schema fixes both:

- `trades_group` gets a `version UInt64` column and
  `ENGINE = ReplacingMergeTree(version)`; the app writes strictly increasing
  versions, so the latest state of a trade (e.g. its "close" row) always wins,
  deterministically.
- Both tables order by `(transaction_hash, pair_name, trade_datetime)`.
- Reads use `FINAL` (see `fetch_last_group_trades`).

> Deploy order: **migrate the tables before deploying the new code.**
> The new code tolerates the old table (the extra `version` field is ignored
> by the driver), but the old code cannot insert into the new
> `trades_group` (missing `version` key → `KeyError`).

## SQL

Adjust `watcher` / table names to your deployment (`clickhouse.database`,
`clickhouse.table`; the groups table is `trades_group` by default).

### 1. `trades` table

```sql
CREATE TABLE watcher.trades_new
(
    `transaction_hash` String,
    `trade_datetime`   DateTime,
    `block_number`     UInt32,
    `pair_name`        String,
    `base_token`       String,
    `quote_token`      String,
    `amount_base`      Float64,
    `amount_quote`     Float64,
    `price`            Float64,
    `type`             String,
    `sender`           String
)
ENGINE = ReplacingMergeTree
ORDER BY (transaction_hash, pair_name, trade_datetime);

-- FINAL drops the duplicates left by unmerged inserts / overlapping re-scans
INSERT INTO watcher.trades_new
SELECT transaction_hash, trade_datetime, block_number, pair_name,
       base_token, quote_token, amount_base, amount_quote, price, type, sender
FROM watcher.trades FINAL;

RENAME TABLE watcher.trades TO trades_old, watcher.trades_new TO trades;
-- after verifying everything looks right:
-- DROP TABLE watcher.trades_old;
```

### 2. `trades_group` table

The status is recomputed during the migration ("only the last trade of a
group is `open`"), which also **repairs the duplicated open/close rows** you
currently see:

```sql
CREATE TABLE watcher.trades_group_new
(
    `transaction_hash` String,
    `trade_datetime`   DateTime,
    `pair_name`        String,
    `group`            String,
    `gain_base`        Float64,
    `gain_quote`       Float64,
    `pct_price_change` Float64,
    `status`           String,
    `version`          UInt64 DEFAULT 0
)
ENGINE = ReplacingMergeTree(version)
ORDER BY (transaction_hash, pair_name, trade_datetime);

-- FINAL collapses each trade's duplicate open/close rows, and the window
-- function restores the correct status: 'open' for the group's last trade,
-- 'close' for every other trade.
INSERT INTO watcher.trades_group_new
SELECT
    transaction_hash,
    trade_datetime,
    pair_name,
    `group`,
    gain_base,
    gain_quote,
    pct_price_change,
    if(row_number() OVER (PARTITION BY `group` ORDER BY trade_datetime DESC, transaction_hash DESC) = 1,
       'open', 'close') AS status,
    toUInt64(1) AS version
FROM watcher.trades_group FINAL;

RENAME TABLE watcher.trades_group TO trades_group_old, watcher.trades_group_new TO trades_group;
-- after verifying everything looks right:
-- DROP TABLE watcher.trades_group_old;
```

## Verify

```sql
-- no trade should appear more than once
SELECT transaction_hash, pair_name, trade_datetime, count() AS c
FROM watcher.trades_group
GROUP BY transaction_hash, pair_name, trade_datetime
HAVING c > 1;

-- only the last trade of each group is open
SELECT `group`, groupArray(status)
FROM (SELECT `group`, status
      FROM watcher.trades_group FINAL
      ORDER BY trade_datetime)
GROUP BY `group`;
```
