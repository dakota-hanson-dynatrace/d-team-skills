# DPS rate card, DEM Insights split, discount tiers, and FX

## Full current US list rate card

Source: "Model DPS based on usage" sheet, column Y (hardcoded USD list price per the stated
volume). Column Z = `ROUNDUP(Y * exchange_rate, 0)` — the FX-adjusted, rounded-up rate actually
used downstream. At `selected_country` = US, `exchange_rate` = 1, so Z = Y exactly.

| Capability | Unit | List price |
|---|---|---|
| Full-Stack Monitoring | memory-GiB-hours | $1,000 / 100,000 |
| Infrastructure Monitoring | host-hours | $4,000 / 100,000 |
| Foundation & Discovery | host-hours | $1,000 / 100,000 |
| Kubernetes Platform Monitoring | pod-hours | $200 / 100,000 |
| Container Application Monitoring | container-hours | $700 / 100,000 |
| Code Monitoring | container-hours | $500 / 100,000 |
| Database Monitoring[^dbmon] | db-instance-hours | $1,100 / 10,000 |
| Mainframe Monitoring | MSU-hours | $1,000 / 10,000 |
| Log Mgmt - Ingest & Process | gibibytes | $2,000 / 10,000 |
| Log Mgmt - Retain | gibibyte-days | $700 / 1,000,000 |
| Log Mgmt - Query | gibibytes-scanned | $3,500 / 1,000,000 |
| Log Mgmt - Retain w/ Included Queries | gibibyte-days | $20,000 / 1,000,000 |
| Metrics - Ingest & Process | metric data points | $150 / 100,000,000 |
| Metrics - Retain | gibibyte-days | $700 / 1,000,000 |
| Metrics - Query | gibibytes-scanned | $0 (included) |
| Traces - Ingest & Process | gibibytes | $2,000 / 10,000 |
| Traces - Retain | gibibyte-days | $700 / 1,000,000 |
| Traces - Query | gibibyte-scanned | $3,500 / 1,000,000 |
| Events - Ingest & Process | gibibytes | $2,000 / 10,000 |
| Events - Retain | gibibyte-days | $700 / 1,000,000 |
| Events - Query | gibibyte-scanned | $3,500 / 1,000,000 |
| Runtime Vulnerability Analytics (RVA) | memory-GiB-hours | $225 / 100,000 |
| Runtime Application Protection (RAP) | memory-GiB-hours | $225 / 100,000 |
| Security Posture Management (SPM) | host-hours | $700 / 100,000 |
| RUM with Insights | sessions | $300 / 100,000 |
| RUM with Session Replay with Insights | session replay captures | $600 / 100,000 |
| RUM Property with Insights | properties/session | $10 / 100,000 |
| Browser Monitor/Clickpath with Insights | synthetic actions | $600 / 100,000 |
| 3rd-Party Synthetic API Ingestion with Insights | results | $133 / 100,000 |
| HTTP Monitor with Insights | synthetic requests | $133 / 100,000 |
| Automation Workflow | workflow-hours | $300 / 10,000 |
| Data Egress | gibibytes-egressed | $1,500 / 10,000 |
| Agentic AppEngine Standard Function Calls | invocations | $1,000 / 1,000,000 |
| AI Units | units | $1,000 / 10,000 |
| Custom Metrics Classic | metric data points | $200 / 100,000,000 |
| Log Monitoring Classic | log records | $100 / 100,000,000 |
| Custom Traces Classic (OpenTelemetry) | spans | $140 / 100,000,000 |
| Custom Events Classic | custom events | $200 / 100,000,000 |
| Serverless Functions Classic | invocations | $400 / 100,000,000 |

[^dbmon]: **This line is not "the" database monitoring rate — it's one of two.** Per
    [docs.dynatrace.com/docs/license/capabilities/app-infra-observability/database-monitoring](https://docs.dynatrace.com/docs/license/capabilities/app-infra-observability/database-monitoring),
    native Database Monitoring (this db-instance-hour line) currently only covers instances monitored
    by the PostgreSQL or MySQL extension, and has no customer-facing polling-interval setting — it
    bills continuous db-instance-hours regardless of poll cadence. Oracle, SQL Server/MSSQL, DB2 LUW,
    SAP HANA, etc. aren't eligible for this line and are billed as ordinary custom metrics (Metrics -
    Ingest & Process or Custom Metrics Classic rows below) through the classic OneAgent/ActiveGate
    extension, which does have a configurable poll interval. A sizing summary that states an explicit
    polling interval (e.g. "N instances, polled every 5 minutes") is describing the classic-extension
    product, not this line — see `estimator-mechanics.md`'s Database Monitoring section for the full
    decision rule and per-engine metric-count constants.

## DEM "with Insights" vs "without Insights" — a second rate tier most people miss

The six DEM rows above are the **"with Insights"** rates. "Show the Discount" (Pricing Tool)
carries a toggle, `Discont_helper_DEM_Insights`, that swaps all six between the "with Insights"
columns (Z67:Z72) and a cheaper **"without Insights"** set (Z58:Z63) — about a 33% difference on
most lines:

| Capability | With Insights | Without Insights |
|---|---|---|
| RUM | $300 / 100,000 sessions | $225 / 100,000 sessions |
| RUM with Session Replay | $600 / 100,000 captures | $450 / 100,000 captures |
| RUM Property | $10 / 100,000 | $10 / 100,000 (same) |
| Browser Monitor/Clickpath | $600 / 100,000 actions | $450 / 100,000 actions |
| 3rd-Party Synthetic API Ingestion | $133 / 100,000 results | $100 / 100,000 results |
| HTTP Monitor | $133 / 100,000 requests | $100 / 100,000 requests |

Which tier applies is a commercial decision (whether Davis AI/Insights is part of the deal), not a
formula — confirm which one a given estimate used before comparing numbers. "Model DPS using
classic prices" has its own `with_insights`/`isWithInsights` toggle (B7) and dedicated discount
named ranges (`classic_discount_DEM`, `classic_discount_DEM_Insights`) driving the same split.

## Commit-tier discount reference table

For rep guidance only — **not auto-applied by any formula**. `RateDiscount` (named range, cell
AK5 on "Model DPS based on usage") is a manual input the rep sets themselves after picking a tier
here. "Quick Price Estimate" and "Model DPS using classic prices" each carry their own copy of this
same table (confirmed identical breakpoints and percentages across all three locations) and
auto-look-up the tier from the annual commit the rep enters, but the rep still typically layers an
additional negotiated discount on top.

| Tier | Annual commit (USD) | Discount |
|---|---|---|
| 1 | $0 – $49,999.99 | 0% |
| 2 | $50,000 – $99,999.99 | 2% |
| 3 | $100,000 – $199,999.99 | 5% |
| 4 | $200,000 – $299,999.99 | 10% |
| 5 | $300,000 – $499,999.99 | 15% |
| 6 | $500,000 – $699,999.99 | 20% |
| 7 | $700,000 – $999,999.99 | 25% |
| 8 | $1,000,000 – $1,299,999.99 | 30% |
| 9 | $1,300,000 – $1,599,999.99 | 33% |
| 10 | $1,600,000 – $1,999,999.99 | 36% |
| 11 | $2,000,000 – $2,999,999.99 | 40% |
| 12 | $3,000,000 – $3,999,999.99 | 45% |
| 13 | $4,000,000 – $5,999,999.99 | 50% |
| 14 | $6,000,000+ | 55% |

## FX / currency (Weighting Tables sheet)

`exchange_rate` (named range, `'Weighting Tables'!O2`) = `VLOOKUP(selected_country, J1:L37, 3, 0)`,
where `selected_country` mirrors `Start!G2`. Every list rate (column Z) is
`ROUNDUP(Y * exchange_rate, 0)` — **pick a non-US country and every displayed per-unit rate
changes and rounds up; that's expected, not a data error.** 36 countries are listed; representative
rates (local currency units per 1 USD):

| Country/region | Currency | Rate |
|---|---|---|
| United States | USD | 1 |
| United Kingdom | GBP | 0.75677 |
| Eurozone | EUR | 0.87198 |
| Canada | CAD | 1.39424 |
| Australia | AUD | 1.45869 |
| Japan | JPY | 159.65107 |
| India | INR | 93.99176 |
| Brazil | BRL | 5.2521 |
| China | CNY | 6.90899 |
| LATAM / MEA / Macau / VPT regions | USD | 1 (pegged, USD-denominated) |

For a country not listed here, read `'Weighting Tables'!J1:L37` directly in the source workbook —
this table is illustrative, not exhaustive.

The rest of Weighting Tables (rows A1–A51) holds **legacy classic-SKU weighting factors** (Host
Unit, DEM Unit, Davis Data Unit, Application Security Unit) used only by "Model DPS using classic
prices" for converting an existing classic contract — they don't feed the usage-based DPS engine
and aren't part of the rate card above.
