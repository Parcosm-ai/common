# Market Data Overview

A clockwork of data ingestion, processing, storage and retrieval with the goal of providing data about financial markets, as described below.

## **Market Data Surfaced** For Analysis, Applications, MCP, APIs etc

1. Historical: closing prices (adjusted or unadjusted) per company and date
2. Intraday: prices during the day (typically unadjusted) per company and minute
3. Shares out: Number of shares by company and date
4. Company identifiers (parcosm ID, symbol, figi, cusip, CIK, ...) by date
5. Is market day? functions to tell if markets are open, when the last market day was, if a certain date was a market date etc.
6. Corporate actions (dividends, splits, shares emitted etc)

## Requirements

1. **Provider agnostic**. Diferent vendors and providers provide different data slices, granularity, and update rules. Examples:

   - Databento US.MINI doesn't provide splits information
   - marketstack data for AAMI is 10 days behind

2. **Proper ID**. The "symbol" used by markets is an ambiguous identifier.

   - V is Visa since 2008, was Vivendi prior to 2006

3. **Symbol Discovery**. As new companies/"symbols" are added, they should go live in our data and apps.

   - SpaceX "SPCX" going live on June 12 2026

4. **Data Merging Business Logic**. As vendor data overlap and may contradict each other, there must be clear logic (code) to retrieve the preferred one and handle failures and gaps.

   - "IF x does not exist from vendor A, try B"

5. **Data Adjustment Business Logic**. When splits and dividends occurr, backdated values may need to be adjusted wrt what they were at the time.

6. **Access Layer**. Data users, such as agents and apps, should retrieve the data via accessors, never querying the database directly.

### Data Providers/Ingestors

- **MarketStack**
  - Project: `marketstack2`
  - Table prefix: `market_data`
  - Status: `live`
  - Notes: Closing data, splits and dividends, symbol-based, 20+ years historical coverage, unreliable, per-symbol download

- **Databento**
  - Project: `databento`
  - Table prefix: `dbento`
  - Status: `live`
  - Notes:
    - Closing data, no splits, symbol-based, less history, more reliable, per-day download (all symbols)
    - Live market data including extended hours

- **OpenFigi**
  - Project: `openfigi`
  - Table prefix: `ofigi`
  - Status: `live`
  - Notes: FIGI IDs, per symbol and per date

- **SEC**
  - Project: `edgar`
  - Table prefix: `sec`
  - Status: `live`
  - Notes: Disclosures and filings, require open text parsing, always a work in progress

### Data Needs

- **Historical closing values ("ohlcv")**
  - Mostly available with some gaps
  - Sources: Marketdata `/close`, Databento `"ohlcv"`
  - May require stitching multiple providers

- **Daily intraday values**
  - Available from Databento at 1-minute intervals
  - No historical coverage beyond 30 days

- **Shares out**
  - Problematic
  - Mostly unavailable/incomplete
