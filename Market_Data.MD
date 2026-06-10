# Market Data Architecture 

Market data is one of the most sensitive parts of the Parcosm data architecture. 

Requirements:

1. **Provider agnostic**. Diferent vendors and providers provide different data slices, granularity, and update rules. Examples:

** databento US.MINI doesn't provide splits information
** marketstack data for AAMI is 10 days behind

2. **Proper ID**. The "symbol" used by MarketData as well as DataBento is ambiguous:

** V is Visa since 2008, was Vivendi prior to 2006

3. **Symbol Discovery**. As new companies/"symbols" are added, they should go live in our data and apps.


