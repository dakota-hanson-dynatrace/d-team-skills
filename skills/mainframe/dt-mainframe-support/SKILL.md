---
name: dt-mainframe-support
description: >
  Mainframe + Dynatrace technical support knowledge. Use when the user asks about CICS, IMS,
  DB2, MQ, z/OS, abends, ASRA, S0Cx codes, zDC, zRemote, PLT tables, CICSPlex, or mainframe log
  collection/monitoring with Dynatrace. Covers CICS architecture (zDC/zRemote stack, PLT/CSD
  region setup), MQ on z/OS, the CICS/Mainview UOWID correlation mismatch, log ingest setup, and
  S0Cx abend diagnosis (S0C1/2/4/5/6/7). Always explain *why* something happens, not just what to
  do. Does not cover Dynatrace-vs-competitor positioning (MainView, OMEGAMON, SYSVIEW, STROBE) -
  see dt-mainframe-competitive for that.
---

# Mainframe Support Context

You are a mainframe + Dynatrace expert. When anyone asks about CICS, IMS, DB2, MQ, z/OS, abends, ASRA, S0Cx codes, log collection, zDC, PLT tables, or mainframe monitoring with Dynatrace, answer using the knowledge below. Always explain *why* something happens, not just what to do.

---

## CICS Architecture & Interface

### Core Three-Layer Stack

1. **CICS module (code module)** — installs directly into each CICS region. Hooks into CICS transactions and writes monitoring data to a Shared Memory Object (SMO).
2. **z/OS Data Collector (zDC)** — a z/OS subsystem that runs per LPAR and manages the SMO. All code modules (CICS, IMS, z/OS Java) write into it.
3. **zRemote module (on ActiveGate)** — runs on an ActiveGate (typically Linux/Windows) and pulls data from the zDC over the network, forwarding it to the Dynatrace platform.

### What Dynatrace Monitors for CICS

- **Transaction tracing** — end-to-end, including CICS Transaction Gateway, z/OS Connect EE, IBM MQ, HTTP/SOAP/JSON, or 3270 terminals
- **Distributed traces** — full PurePaths spanning mobile/web frontends down into mainframe programs
- **File access** — VSAM and other file access by CICS applications
- **Logs** — CICS region logs via MSGUSR DD
- **Db2 calls** — DB2 interactions from CICS transactions (visible in PurePaths)
- **CICSPlex grouping** — groups multiple CICS regions into a single process group

### Transaction Start Points

Configured in **Settings > Mainframe > Transaction start filters**. Transactions are traced when initiated by:
- Monitored upstream services (automatic)
- CICS Transaction Gateway
- z/OS Connect EE
- IBM MQ
- Explicitly listed transaction IDs (for 3270 terminal-initiated or standalone mainframe transactions)

**Overhead:** Typically 1-2% GCP on the LPAR (verify against current docs for your OneAgent version - this figure moves release to release).

### What Changes at the CICS Region Level (No App Code Changes Needed)

App developers don't touch COBOL/PL/I/Assembler programs. All instrumentation hooks at the CICS exit/PLT level. The CICS/systems admin makes these changes:

1. **PLT entries** — Add `ZDTPLT` to PLTPI table (after DFHDELIM); add `ZDTPLTSD` to PLTSD table. DFHDELIM marks the boundary between IBM's internal programs and customer/vendor programs.
2. **DFHRPL concatenation** — Add `SZDTLOAD` to the CICS region's DFHRPL DD, or define as a CICS library resource in the CSD.
3. **CSD resource definitions** — Install Dynatrace CICS resources from sample member `CICRDO` in `SZDTSAMP` (defines ZDTPLT, ZDTSOAPH, DTAX transaction).
4. **SOAP/JSON pipeline configs** — Add `ZDTSOAPH` as a `<headerprogram>` in pipeline XML config files (only if using CICS SOAP or non-Java JSON pipelines).
5. **CTS 6.2 only** — Add `DFHBPZDT` from `SZDTAUTH` to LPA (APF-authorized).

### MQ on z/OS

The CICS agent captures MQ operations (MQGET, MQPUT, etc.) as part of traces. Separately, the MQ Extension for MQ Observability runs on an ActiveGate and pulls MQ metrics remotely from MQ on z/OS.

### Davis AI / Adaptive Thresholds on Mainframe

- Telemetry pipes via zDC → ActiveGate → Dynatrace platform (no standard OneAgent)
- Davis AI automatically creates baseline cubes once mainframe metrics are ingested
- Thresholds recalibrate every 24 hours automatically

### UOW Correlation Issue (CICS UOWID)

Known mismatch between Dynatrace and Mainview for the same Unit of Work:

| | Dynatrace (Field 132) | Mainview (Field 098) |
|---|---|---|
| Field | RMUOWID | NETUOWSX |
| Type | Binary (TYPE-T) | Character (TYPE-C) |
| Scope | Internal RM identifier | Network/distributed |
| Cross-system portable | No | Yes |

Direct correlation between Dynatrace PurePaths and Mainview transaction records requires a mapping layer — they use different CMF fields to identify the same UOW.

---

## Log Collection

### CICS Log Collection Setup

**Step 1: Activate log ingest rule**
1. Navigate to **Settings > Log Monitoring > Log ingest rules**
2. Activate the built-in rule: **z/OS CICS message user**
3. This collects logs from the **MSGUSR DD statement** in IBM CICS regions

**Step 2: Configure log sources (optional)**
- Log source: `z/OS CICS message user`
- Log record level: ERROR, WARN, or other severity as needed
- Scope: Limit to specific LPARs (hosts) or host groups if required

**Step 3: Mask sensitive data (optional)**
Configure data masking rules before logs are ingested.

**Step 4: Analyze collected logs**
- View in **Log Viewer** (auto-enriched with metadata)
- Link to z/OS Host pages for context
- Use **Notebooks with DQL** for advanced analysis — see the `dtctl` and `dt-dql-essentials` skills for query syntax and CLI usage
- Correlate with traces for end-to-end visibility

**Requirements:**
- OneAgent version **1.291+** with CICS module installed on each CICS region (verify current minimum against docs.dynatrace.com — this floor rises over time)
- Log Management and Analytics license (Platform Subscription or Davis data units)

### IMS Log Collection

Follow the same pattern — look for built-in rules under **Settings > Log Monitoring > Log ingest rules** filtered by `z/OS IMS`.

### DB2

DB2 call data is captured as part of CICS transaction traces (not separate log streams). DB2 interactions are visible in PurePaths under the CICS transaction that made the call.

---

## Mainframe Abend Codes

### ASRA — CICS Program Interrupt

ASRA is a CICS program interrupt abend caused by a hardware-level program check within a CICS task. In batch, the OS raises the S0Cx directly. In CICS, the kernel intercepts it and re-raises as ASRA so CICS can handle cleanup and rollback without crashing the entire region.

Underlying S0Cx codes that produce ASRA:

| Code | Name | Description |
|---|---|---|
| S0C1 | Operation exception | Bad/invalid instruction |
| S0C2 | Privileged operation | Privileged instruction in problem state |
| S0C4 | Protection exception | Storage violation (bad address) |
| S0C5 | Addressing exception | Address outside valid range |
| S0C6 | Specification exception | Misaligned or invalid operand |
| S0C7 | Data exception | Invalid packed decimal data (most common) |

**Diagnosing ASRA:** The CICS job log and transaction dump show the offset in the load module, PSW, registers, and specific interrupt code. Use CEDF, CICS transaction dump formatter, or Fault Analyzer to find the source line.

---

### S0C7 — Data Exception (Most Common ASRA Cause)

Packed decimal arithmetic on a field that doesn't contain valid packed decimal data.

**Common causes:**
- Field moved from a file or BMS map without initialization before COMPUTE or ADD
- MOVE SPACES to a numeric working-storage field before arithmetic
- VSAM record field that's blank or uninitialized

**Typical fix:** Initialize the field to numeric zeros before arithmetic:
```cobol
MOVE ZEROS TO WS-NUMERIC-FIELD
```

---

### S0C2 — Privileged Operation Exception

A program attempted to execute a privileged instruction while in problem state (user mode). Almost always a **wild branch** — the program ends up executing bytes that aren't real instructions, and the CPU decodes them as privileged.

**Common causes:**
- Branch to an invalid address landing on a privileged instruction (corrupted pointer or bad BALR/BASR)
- Overlay of a register or return address causing execution to jump into garbage
- Missing RETURN/GOBACK causing fall-through into unintended memory

**Diagnosing:**
1. PSW address in the dump — where was the CPU executing?
2. Compare to load module map — is it even *in* your program?
3. Check base registers for corruption
4. Look backwards for last valid code — often a bad CALL/PERFORM target or missing STOP RUN

In CICS: surfaces as ASRA with interrupt code identifying it as S0C2.

---

### S0C4 — Protection Exception (Storage Violation)

A program tried to read from or write to a storage address it's not authorized to access.

**Two flavors:**
- **Fetch protection** — tried to *read* protected storage
- **Store protection** — tried to *write* protected storage (more common)

**Common causes:**
- **Null pointer / zero address** — referencing address 0 or near 0 (uninitialized pointer)
- **Wild branch** — corrupted return address or base register
- **Array/table overrun** — indexing past the end of a table
- **Deallocated storage** — referencing a GETMAIN'd area after FREEMAIN
- **Stale CICS pointer** — bad ADDRESS OF, stale BLL cell, or uninitialized pointer passed to called program

**Diagnosing:**
1. PSW address — where was the program executing?
2. **Translation Exception Address (TEA)** — the key field. Exactly what address the program tried to touch.
   - Near 000000 → classic null pointer
   - Wild value → register corruption
3. Check registers for where the bad address came from
4. Work backwards to find what corrupted the pointer or index

**S0C4 vs S0C7 rule of thumb:**
- S0C7 → bad *data* (non-numeric in numeric field)
- S0C4 → bad *address* (pointing somewhere illegal)

---

## Quick Diagnosis Checklist

1. Is it ASRA? → Look at the dump for the underlying S0Cx interrupt code
2. S0C7? → Check packed decimal fields for uninitialized data before arithmetic
3. S0C4? → Check the TEA for null/wild address; look for stale pointers or table overruns
4. S0C2? → Look for wild branch; check if PSW address is even within your program
5. All S0Cx → Check PSW + registers in the dump; use Fault Analyzer or CEDF for source-level diagnosis

---

## Useful Links

- [z/OS monitoring overview](https://docs.dynatrace.com/docs/ingest-from/dynatrace-oneagent/installation-and-operation/zos/monitoring)
- [Customize CICS and IMS monitoring](https://docs.dynatrace.com/docs/ingest-from/dynatrace-oneagent/installation-and-operation/zos/operation/cics-ims-monitoring)
- [Install the CICS module](https://docs.dynatrace.com/docs/ingest-from/dynatrace-oneagent/installation-and-operation/zos/installation/install-cics)
