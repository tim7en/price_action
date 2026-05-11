# Point-In-Time Sector Holdings

Stock-level sector rotation must use holdings that were known at the decision date.
Do not backtest historical sector leaders with today's top holdings.

## Required File

Create:

```text
data/sector_top_holdings.csv
```

Required columns:

```text
as_of_date,known_from_date,sector_symbol,holding_symbol,weight,source
```

- `as_of_date`: date the ETF/index holdings snapshot represents.
- `known_from_date`: first date the strategy could have known the snapshot.
- `sector_symbol`: sector ETF, for example `XLK`, `XLF`, `XLE`.
- `holding_symbol`: stock symbol held by that sector at that snapshot.
- `weight`: holding weight as either decimal (`0.1234`) or percent (`12.34`).
- `source`: optional audit string such as issuer archive URL, SEC accession, or vendor snapshot id.

The backtest uses only rows where:

```text
known_from_date <= signal_date
```

For each selected sector and rebalance date, it takes the latest known snapshot and normalizes the top five available holdings inside that sector sleeve.

## Build From SEC N-PORT

For the Select Sector SPDR funds, public SEC N-PORT filings can build this file from late 2019 onward:

```bash
.venv/bin/python build_sector_top_holdings_from_sec.py --refresh-prices
```

The builder caches SEC XML filings under `cache/sec_nport/`, maps SEC CUSIP/ISIN identifiers to Yahoo symbols through `cache/sec_identifier_symbol_map.json`, writes coverage to `outputs/sector_rotation_report/sector_top_holdings_coverage.csv`, and writes unresolved symbol mappings to `outputs/sector_rotation_report/sector_top_holdings_symbol_gaps.csv`.

Mapped symbols that no longer have Yahoo chart history, such as acquired or delisted former constituents, are written to `outputs/sector_rotation_report/sector_top_holdings_price_gaps.csv`. The backtest excludes those unavailable symbols at execution time and records them in `missing_top_holding_symbols`.

This does not solve the full 2006-2019 history. For that older period we still need historical issuer archives, Form N-Q parsing, or a point-in-time vendor feed.

## Date Discipline

Use issuer-published daily holdings if you have an archive. If the archive does not preserve publication time, set `known_from_date` conservatively to the next trading day.

If using SEC filings:

- for Form N-PORT, use the EDGAR filing or acceptance date as `known_from_date`, not the report period end
- for older history before N-PORT, use Form N-Q or a point-in-time vendor feed

Using `as_of_date` as the decision date when the holdings were only published later creates lookahead bias.

## Gold

Gold should not be treated as a company inside any equity sector. The no-lookahead ETF test models `GLD` as a separate investable sleeve in `backtest_etf_gold_rotation.py`.
