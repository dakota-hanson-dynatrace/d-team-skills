---
name: dt-mainframe-competitive
description: >
  Use when comparing Dynatrace OneAgent zDC to BMC MainView, IBM OMEGAMON, CA SYSVIEW, or
  Compuware STROBE for mainframe monitoring. Covers the system-monitoring-vs-application-
  observability positioning, capability comparison tables, and "customers use both" framing.
  Triggers on "Dynatrace vs MainView", "OMEGAMON comparison", "mainframe monitoring tools
  comparison", "STROBE alternative", "why isn't Dynatrace showing LPAR CPU". For mainframe
  technical/architecture questions (CICS, abends, log collection, zDC setup) see
  dt-mainframe-support instead.
---

# Mainframe Competitive Comparison

When asked to compare Dynatrace to BMC MainView, IBM OMEGAMON, CA SYSVIEW, or Compuware STROBE for mainframe monitoring, use this breakdown. The key distinction is **system monitoring** (infrastructure/subsystem health) vs. **application observability** (transactions, traces, AI).

### The Core Difference

- **BMC MainView, IBM OMEGAMON, CA SYSVIEW** — traditional **system monitors**. They excel at LPAR health, subsystem status, batch/JES queues, and SMF data. They do not trace individual transactions or provide distributed traces.
- **Compuware STROBE** — a **code-level profiler**. It samples CPU usage at the program/statement level to find hotspots, but is not a transaction tracer and has no distributed trace capability.
- **Dynatrace OneAgent zDC** — an **application observability** platform. It traces transactions end-to-end from mobile/web through z/OS, provides AI-powered root cause analysis, and streams telemetry to cloud analytics. It does not replace infrastructure system monitors for LPAR/subsystem health metrics.

### System Monitoring (Infrastructure & Subsystem Health)

| Capability | BMC MainView | IBM OMEGAMON | CA SYSVIEW | Compuware STROBE | Dynatrace OneAgent zDC |
|---|---|---|---|---|---|
| Host / LPAR CPU, Memory & I/O metrics | Yes | Yes | Yes | No | No |
| Subsystem health (CICS, DB2, MQ, IMS) | Yes | Yes | Yes | No | No |
| Batch job & JES queue monitoring | Yes | Yes | Yes | No | No |
| Storage, network & SMF data collection | Yes | Yes | Yes | No | No |

**Why Dynatrace doesn't cover these:** Dynatrace uses the zDC (z/OS Data Collector) architecture focused on application-level telemetry — transactions, traces, and code paths. Infrastructure-level z/OS metrics (LPAR CPU, SMF records, JES queues) are the domain of traditional system monitors. Many customers run Dynatrace **alongside** MainView/OMEGAMON/SYSVIEW — not instead of them.

### Application Observability (Transactions, Traces & AI)

| Capability | BMC MainView | IBM OMEGAMON | CA SYSVIEW | Compuware STROBE | Dynatrace OneAgent zDC |
|---|---|---|---|---|---|
| Transaction-level tracing (CICS / IMS) | No | No | No | Partial* | Yes |
| Code-level profiling & hotspot analysis | No | No | No | Yes | Yes |
| End-to-end distributed trace (z/OS → cloud) | No | No | No | No | Yes |
| Cross-tier topology & dependency map | No | No | No | No | Yes |
| AI-powered root cause analysis | No | No | No | No | Yes |
| Real-time streaming to cloud analytics | No | Partial** | No | No | Yes |

*Compuware STROBE provides CPU sampling at the transaction level but is not a full transaction tracer — it does not correlate into distributed traces or propagate context across tiers.

**IBM OMEGAMON has some streaming/export capability but is not designed as a real-time cloud analytics platform.

### Positioning Summary

| Tool | Best For | Not Designed For |
|---|---|---|
| **BMC MainView** | LPAR health, CICS/DB2/MQ subsystem status, real-time operator console | Transaction tracing, distributed traces, AI root cause |
| **IBM OMEGAMON** | z/OS infrastructure monitoring, historical capacity planning | Application-level traces, cross-tier topology |
| **CA SYSVIEW** | Real-time z/OS system monitoring, SMF analysis | Transaction tracing, cloud integration |
| **Compuware STROBE** | CPU hotspot profiling, code-level performance tuning | Distributed traces, AI analysis, real-time streaming |
| **Dynatrace OneAgent zDC** | End-to-end transaction traces, AI root cause, cloud integration | LPAR/subsystem infrastructure metrics, JES/batch monitoring |

### When Customers Use Both

Most large mainframe shops use Dynatrace **complementary** to their existing tools, not as a replacement:
- MainView/OMEGAMON/SYSVIEW handle the "is the LPAR healthy?" question
- Dynatrace answers "why did this transaction fail, and what was the full path across every tier?"
- STROBE handles deep CPU profiling per module; Dynatrace shows which transactions are slow and where across the entire stack
