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

4. **Data Merging Business Logic**  As vendor data overlap and may contradict each other, there must be clear logic (code) to retrieve the preferred one and handle failures and gaps

  - "IF x does not exist from vendor A, try B" 

5. **Data Adjustment Business Logic**  When splits and dividends occurr, backdated values may need to be adjusted wrt what they were at the time

6. **Access Layer** Data users, such as agents and apps, should retrieve the data via accessors, never querying the database directly. 





### Data Providers/Ingestors

| Name | Project | Table prefix | Status | Notes |
|------|---------|--------------|--------|-------|
| MarketStack | marketstack2 | market_data | live | Closing data, splits and dividends, symbol-based, 20+ years historical coverage, unreliable, per-symbol download |
| Databento | databento | dbento | live | Closing data, no splits, symbol-based, less history, more reliable, per-day download (all symbols) |
| Databento | databento | dbento | live | Live Market Data including extended hours |
| OpenFigi | openfigi | ofigi | live | FIGI IDs, per symbol and per date |
| SEC | edgar | sec | live | Disclosures and filings, require open text parsing, always a work in progress |

### Data Needs

| Kind of data | Status |
|--------------|--------|
| Historical closing values ("ohlcv") | mostly available with some gaps (Marketdata /close, Databento "ohlcv") may require stitching multiple providers |
| Daily "intraday" values | available from databaento at 1m intervals, no historical coverage beyond 30 days |
| Shares out | problematic. License/pricing limitations from DataBento. Unclear when disclosures get filed into SEC |
| Historical FIGI mappings | problematic. We may need a TSV with hand-coded exceptions if a data provider can't be found |


## Data Layers 

1. Raw Data Tables - These are created by ingestors (see below) and reflect what the data provider provided on the date
2. Clean Data Tables  - These to be created to reflect Parcosm's ground truth. 
3. Accessors - used by apps & agents, see *Market Data Surfaced** section. 


## Ingestor Status

1. **Marketsack Ingestor** Existing: Github marketstack2. Crontab. Obtains daily closing data after midnight. Table prefix market_data
2. **DataBento Ingestor** Existing: Github databento. Crontab. Obtains daily closing data after midnight and live minute-by-minute quotes during market hours. Table prefix dbento
3. **OpenFigi Ingestor** Existing: GitHub openfigi. On-Demand. Fetches FIGI Ids and saves them in database table. YOU MUST CALL IT TO REFRESH THE LIST EVERY DAY. Table prefix ofigi. 

NOTE: both markestack & databento ingestors call openfigi to make sure the symbols we receive from this providers are refreshed on our openfigi tables. 

## Data Stitching Logic (stub)

1. TO get (closing) for (parcosm id) from date1 to date2, adjusted:

    1. for each data provider for (closing):

        1. find mapping(s) from parcosm id to data provider's own indexing (e.g. symbol) 

            - for example: Parcosm ID "111" 
           - -> Marketstack "SPCK" (from 2026-05-01) "SPCX" (pre 2026-05-01)
           - -> DataBento "SPCK" (from 2026-05-01)

        2. identify date ranges available in our database using the mappings above

           - example: marketstack tables have this data from 2001 to present day, databento tables from 2026-05-01 to today

        3. retrieve the data matching dates requested with preferred providers

            - for example: use  Databento for 2026-05-01 to data2, fall back to marketdata for date1 - 2026-04-30

        4. apply adjustments (if requested)

            - if split data available, match it against the data

            - identify suspicious points (what to do? ignore or wild guess? or return "no data"?) 

