# Market Data Architecture 

Market data is one of the most sensitive parts of the Parcosm data architecture. 

## Requirements

1. **Provider agnostic**. Diferent vendors and providers provide different data slices, granularity, and update rules. Examples:

  - Databento US.MINI doesn't provide splits information
  - marketstack data for AAMI is 10 days behind

2. **Proper ID**. The "symbol" used by MarketData as well as DataBento is ambiguous:

  - V is Visa since 2008, was Vivendi prior to 2006

3. **Symbol Discovery**. As new companies/"symbols" are added, they should go live in our data and apps.

  - SpaceX "SPCX" going live on June 12 2026


4. **Data Merging Business Logic**  As vendor data overlap and may contradict each other, there must be clear logic (code) to retrieve the preferred one and handle failures and gaps

  - "IF x does not exist from vendor A, try B" 

5. **Access Layer** Data users, such as agents and apps, should retrieve the data via accessors, never querying the database directly. 


## Implementation Decisions

### Providers/Ingestors

``
Name          Project        Table_Prefix    Notes
MarketStack   marketstack2   market_data     Closing data, splits and dividends, symbol-based, 20+ years historical coverage, unreliable, per-symbol download
Databento     databento      dbento          Closing data, no splits, symbol-based, less history, more reliable, per-day download (all symbols)
                                             Live Market Data including extended hours

``
