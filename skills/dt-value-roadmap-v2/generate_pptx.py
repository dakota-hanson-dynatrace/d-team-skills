#!/usr/bin/env python3
"""
dt-value-roadmap-v2: Dynatrace Value Roadmap deck generator.
Usage: python3 generate_pptx.py --customer NAME --tenant URL --data data.json [--output FILE]
"""
import argparse, json, os, datetime, sys, zipfile
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR

SKILL_DIR  = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SKILL_DIR)
import tech_discovery
TMPL_FIXED = os.path.join(SKILL_DIR, 'dt_template_fixed.pptx')

# Palette and type follow the Observability Gap Analysis reference deck: white content
# slides, navy titles, grey support text, Arial, blue/purple/magenta accents.
NAVY       = RGBColor(0x1A, 0x24, 0x40)
WHITE      = RGBColor(0xFF, 0xFF, 0xFF)
GREY       = RGBColor(0x6F, 0x74, 0x7F)
BORDER     = RGBColor(0xD7, 0xDA, 0xE0)
PANEL      = RGBColor(0xF8, 0xF9, 0xFA)
BLUE       = RGBColor(0x3B, 0xAC, 0xF0)
ROYAL      = RGBColor(0x19, 0x66, 0xFF)
PURPLE     = RGBColor(0x5E, 0x29, 0xE5)
MAGENTA    = RGBColor(0xC9, 0x3F, 0xDB)
COVER_BG   = RGBColor(0x05, 0x08, 0x16)
LIGHT      = RGBColor(0xF1, 0xF3, 0xF6)
FONT       = 'Arial'

TIER_COLOR = {'Coverage': BLUE, 'Anomaly': PURPLE, 'Config Fix': ROYAL, 'Upgrade': MAGENTA,
              'Start Here': MAGENTA, 'High Value': PURPLE, 'Phase 2': BLUE}
GEN_LABEL  = {'Gen3': 'Gen3 - improve', 'Gen2': 'Gen2 (classic feature)', 'Upgrade': 'Gen2 to Gen3 upgrade',
              'Both': 'Gen2 + Gen3 - consolidate'}

def _join(items, n=4):
    """'A, B, C and 2 more' - keeps tenant name lists slide-sized."""
    items = [str(i) for i in (items or [])]
    if len(items) <= n:
        return ', '.join(items)
    return f"{', '.join(items[:n])} and {len(items) - n} more"

def _n(count, singular, plural=None):
    """'1 service' / '3 services' - every counted noun in finding text goes through this."""
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"

# ── OPPORTUNITY LIBRARY ───────────────────────────────────────────────────────
# Each entry: trigger(data)->bool, priority, and format strings keyed {variable}.
# All format strings are rendered with data.format(**data) at build time.
OPPORTUNITIES = [
    {
        'key': 'oneagent_coverage',
        'trigger': lambda d: d.get('oneagent_fullstack_pct', 100) < 80 or d.get('hosts_infra', 0) > 0,
        'priority': 'Coverage',
        'slide_title': 'Review {hosts_infra} Infrastructure-Only Hosts',
        'card_title':  '{hosts_fullstack} of {hosts_total} OneAgent hosts are FullStack ({oneagent_fullstack_pct}%); {hosts_infra} are Infrastructure-only',
        'next_bullet': 'Review {hosts_infra} Infrastructure-only hosts for FullStack',
        'body': lambda d: (
            f"{d['hosts_fullstack']} of {d['hosts_total']} OneAgent hosts run in FullStack mode "
            f"({d['oneagent_fullstack_pct']}%). The other {d['hosts_infra']} are Infrastructure-only: host metrics "
            "and topology are there, but no process, service, or trace data."
            + (f"\n\nInfra-only hosts: {_join(d['hosts_infra_names'], 3)}." if d.get('hosts_infra_names') else '')
            + "\n\nInfra-only is the right choice for some hosts (appliances, bastions, hosts with no custom code). "
            "Confirm each one is intentional rather than a deployment default."
        ),
        'fix': (
            'Review the Infra-only list with the application owners. Switch to FullStack where the host runs '
            'application code that should appear in traces; leave the rest as-is. Hosts with no OneAgent at all '
            'are covered in a separate finding.'
        ),
        'roadmap_action': 'Confirm or upgrade the {hosts_infra} Infrastructure-only hosts',
        'roadmap_value':  'Trace coverage on every host that runs application code',
    },
    {
        'key': 'log_enablement',
        'trigger': lambda d: d.get('pg_with_logs_pct', 100) < 70 or (
            d.get('log_records_24h', 0) == 0 and d.get('hosts', 0) > 0),
        'priority': 'Coverage',
        'slide_title': lambda d: ('Choose One Log Path per Workload' if d.get('log_external_pct', 0) >= 50
                                  else 'Start Log Ingestion - No Logs Stored Today' if not d.get('log_records_24h')
                                  else f"Extend Log Ingestion - {d.get('pg_with_logs_pct', 0)}% of Process Groups Covered"),
        'card_title':  lambda d: (
            f"{d.get('log_external_pct')}% of log volume arrives through {d.get('log_external_source', 'a forwarder')}; OneAgent log capture covers {d.get('pg_with_logs_pct', 0)}% of process groups."
            if d.get('log_external_pct', 0) >= 50 else
            f"No logs are stored in Dynatrace; none of the {d.get('process_groups', 0):,} process groups send logs to Grail."
            if not d.get('log_records_24h') else
            f"{d.get('pg_with_logs_pct', 0)}% of process groups are streaming logs to Grail; the rest are a blind spot during incidents."),
        'next_bullet': 'Extend log coverage - {pg_with_logs_pct}% of process groups streaming today',
        'label': lambda d: ('Pick one log path per workload' if d.get('log_external_pct', 0) >= 50 else 'Extend log coverage'),
        # Branches on log_external_pct: when most log volume already arrives via a
        # cloud forwarder (Firehose, Event Hub, etc.), "turn on OneAgent logs" would
        # ingest the same lines twice - the fix becomes "pick one path per workload".
        'body': lambda d: (
            f"{d.get('pg_with_logs_pct', 0)}% of {d['customer']}'s {d.get('process_groups', 0)} process groups send "
            f"OneAgent logs to Grail. {d.get('log_external_pct', 0)}% of log volume arrives through "
            f"{d.get('log_external_source', 'an external forwarder')} instead, with no link to a host, service, "
            "or trace.\n\n"
            "Those application logs are already being ingested, so simply enabling OneAgent log capture for the "
            "same workloads would store every line twice and double log ingest for no extra insight."
            if d.get('log_external_pct', 0) >= 50 else
            f"{d['customer']} does not store any logs in Dynatrace today. None of the {d.get('process_groups', 0):,} "
            "process groups send logs through OneAgent and no forwarder ingest was found, so problems and traces "
            "cannot be tied to the log lines around them."
            if not d.get('log_records_24h') else
            f"{d.get('pg_with_logs_pct', 0)}% of the {d.get('process_groups', 0):,} process groups send logs "
            "to Grail through OneAgent. For the others, an incident investigation has no application logs to "
            "work from in Dynatrace."
            + (f"\n\n{d['log_external_pct']}% of log volume arrives through {d.get('log_external_source', 'a forwarder')}"
               + (f" ({d['log_external_note']})" if d.get('log_external_note') else '')
               + ", so check what each workload already forwards before enabling OneAgent capture for it."
               if d.get('log_external_pct') else '')
        ),
        'fix': lambda d: (
            f"Choose one log path per workload. Either capture with OneAgent (entity- and trace-linked) and drop "
            f"those log groups from {d.get('log_external_source', 'the forwarder')}, or keep the forwarder and add "
            "OpenPipeline enrichment so its logs link to entities. Never run both for the same source."
            if d.get('log_external_pct', 0) >= 50 else
            'Identify the process groups missing from log coverage and confirm log monitoring is enabled on '
            'their hosts (Settings > Log Monitoring). Prioritize production-critical services first.'
        ),
        'dup_guard': lambda d: (
            f"{d.get('log_external_source', 'Forwarded')} logs already cover these workloads - enable OneAgent "
            "capture only where the forwarder copy is switched off."
            if d.get('log_external_pct', 0) >= 50 else
            f"Enable OneAgent capture only for process groups whose logs are not already sent through "
            f"{d.get('log_external_source', 'a forwarder')}." if d.get('log_external_pct') else ''),
        'roadmap_action': lambda d: (
            f"Decide OneAgent or {d.get('log_external_source', 'forwarder')} per workload; switch off the other copy"
            if d.get('log_external_pct', 0) >= 50 else
            f"Enable log monitoring on process groups outside the current {d.get('pg_with_logs_pct', 0)}% coverage"),
        'roadmap_value':  lambda d: ('Trace-linked logs where they matter, with no line stored twice'
                                     if d.get('log_external_pct', 0) >= 50 else
                                     'Root cause data available for the full estate, not just the covered subset'),
    },
    {
        'key': 'log_to_trace',
        # Suppressed when no OneAgent logs exist at all - log_enablement already
        # covers that root cause and a second 0% slide just repeats it.
        'trigger': lambda d: d.get('log_to_trace_pct', 100) < 50 and d.get('pg_with_logs_pct', 0) > 0,
        'priority': 'Coverage',
        'slide_title': 'Enable Log-to-Trace Correlation - Only {log_to_trace_pct}% of Logs Are Linked',
        'card_title':  '{log_to_trace_pct}% of log lines carry a trace ID - the rest need a manual timestamp correlation',
        'next_bullet': 'Link logs to traces - {log_to_trace_pct}% correlated today',
        'body': (
            'Only {log_to_trace_pct}% of {customer}\'s log volume carries a trace ID. For the rest, finding '
            'the log line that explains a slow or failed span means searching by timestamp and hostname by '
            'hand instead of jumping there directly from the trace.\n\n'
            'Log-to-trace correlation is an OneAgent enrichment setting, not a re-instrumentation - most gaps '
            'come from hosts or log sources that predate enrichment being turned on.'
        ),
        'fix': (
            'Enable log-trace correlation under Settings > Log Monitoring > Log enrichment for the sources '
            'currently missing trace IDs. Verify with a DQL query joining logs to spans on the enriched subset.'
        ),
        'roadmap_action': 'Enable log-trace correlation for the {log_to_trace_pct}%-uncorrelated log volume',
        'roadmap_value':  'Collapses RCA time by making every log line one click from its trace',
    },
    {
        'key': 'cloud_coverage_gaps',
        'trigger': lambda d: d.get('cloud_integration_live', False) and (
            d.get('cloud_hosts_without_oneagent', 0) > 0 or d.get('cloud_services_without_logs', 0) > 0),
        'priority': 'Coverage',
        'slide_title': '{cloud_hosts_without_oneagent} Running {cloud_providers_in_use} Instances Have No OneAgent',
        'card_title':  '{cloud_providers_in_use} is connected and discovering resources; {cloud_hosts_without_oneagent} running instances still have no OneAgent',
        'next_bullet': 'Deploy OneAgent to {cloud_hosts_without_oneagent} uncovered {cloud_providers_in_use} instances',
        'body': lambda d: (
            f"The {d.get('cloud_providers_in_use')} integration discovers {d.get('cloud_hosts_running', '?')} running "
            f"instances. {d.get('cloud_hosts_without_oneagent', 0)} of them have no OneAgent"
            + (f": {_join(d.get('cloud_hosts_without_oneagent_names'), 5)}" if d.get('cloud_hosts_without_oneagent_names') else '')
            + (f", and {d['cloud_services_without_logs']} services have no log data" if d.get('cloud_services_without_logs') else '')
            + "."
            + (f"\n\nTraffic confirms the gap: \"Requests to unmonitored hosts\" is the largest service in the "
               f"environment at {d['unmonitored_requests_week']} calls a week. Those calls leave a traced service "
               "and land somewhere OneAgent cannot see." if d.get('unmonitored_requests_week') else '')
            + "\n\nThe cloud integration shows these instances exist and reports CloudWatch metrics for them. It "
            "cannot show what the application on them is doing."
        ),
        'fix': (
            'Add OneAgent to the launch template or AMI for each uncovered Auto Scaling group so new instances '
            'come up instrumented. Leave out instances that are managed services (for example RDS Custom hosts) '
            'where an agent is not supported.'
        ),
        'roadmap_action': 'Add OneAgent to the {cloud_hosts_without_oneagent} uncovered {cloud_providers_in_use} instances',
        'roadmap_value':  'Traces reach the hosts behind the "unmonitored hosts" traffic',
    },
    {
        'key': 'vmware_coverage',
        'trigger': lambda d: d.get('vmware_ext_present', False) and d.get('vmware_hosts', 0) > 0,
        'priority': 'Coverage',
        # vmware_hosts is the ESXi hypervisor count, not guest VMs - wording must say so.
        'slide_title': 'Use VMware Telemetry from {vmware_hosts} ESXi Hosts in Root Cause Analysis',
        'card_title':  '{vmware_hosts} ESXi hosts report hypervisor metrics; guest-level problems can now be traced to host contention',
        'next_bullet': 'Use hypervisor data from {vmware_hosts} ESXi hosts in RCA',
        'label': 'Use ESXi telemetry in root cause analysis',
        'body': lambda d: (
            f"The VMware integration reports hypervisor metrics for {d['vmware_hosts']} ESXi hosts"
            + (f" and {d['vmware_vms']:,} virtual machines" if d.get('vmware_vms') else '')
            + ". That shows when a guest-level slowdown is really host CPU contention, CPU ready time, or "
            "datastore latency."
            + (f"\n\n{d['vmware_problem_note']}" if d.get('vmware_problem_note') else '')
        ),
        'fix': (
            'Add ESXi CPU ready, contention, and datastore latency to the infrastructure dashboards the '
            'operations team already uses, and check the hypervisor view during the next guest-level slowdown '
            'to confirm the correlation path works end to end.'
        ),
        'roadmap_action': 'Bring ESXi contention and datastore metrics into infrastructure dashboards and RCA',
        'roadmap_value':  'Host-layer causes visible for the {vmware_hosts} ESXi hosts behind guest slowdowns',
    },
    {
        'key': 'vmware_data_gap',
        'trigger': lambda d: not d.get('vmware_ext_present', False) and d.get('vmware_ext_intentional') is False,
        'priority': 'Anomaly',
        'slide_title': 'VMware Extension Data Not Found',
        'card_title':  'No VMware extension metrics were found during collection, and this was flagged as unintentional - treat this as an open gap, not a clean bill of health',
        'next_bullet': 'Resolve VMware data gap - extension metrics were expected but not found',
        'body': (
            'This review could not find VMware extension telemetry (vSphere/ESXi entities or metrics) for '
            '{customer}, and the SE running this review confirmed that absence was not intentional.\n\n'
            'Every other finding in this deck that depends on VMware coverage is based on incomplete data - '
            'there may be hypervisor-layer issues (datastore latency, CPU contention) this review simply '
            'cannot see yet.'
        ),
        'fix': (
            'Confirm the VMware extension is deployed and configured against vCenter, and that the ActiveGate '
            'it runs on has network access to the vCenter API. Re-run data collection once metrics are confirmed '
            'flowing before treating VMware coverage as assessed.'
        ),
        'roadmap_action': 'Deploy/fix the VMware extension so vSphere/ESXi metrics begin flowing',
        'roadmap_value':  'Unblocks hypervisor-layer visibility and RCA that this review currently cannot provide',
    },
    {
        'key': 'alert_tuning',
        'trigger': lambda d: d.get('problems_per_day', 0) > 200,
        'priority': 'Start Here',
        'slide_title': '{problems_per_day:,} Problems a Day Is More Than a Team Can Act On',
        'card_title':  '{problems_per_day:,} problems/day across {alerting_profiles} alerting profiles - volume is the signal to tune',
        'next_bullet': 'Tune alerting - {problems_per_day:,} problems/day is too many to act on',
        # Narrative is built from top_problem_sources rather than assuming routing works -
        # alerting_profiles_broken covers profiles that can't fire.
        'body': lambda d: (
            f"Davis opened {d.get('problems_per_week', 0):,} problems in the last 7 days "
            f"({d.get('problems_per_day', 0):,}/day). At that volume even a critical outage risks getting buried."
            + ("\n\nThe volume is concentrated - the top sources are:\n\n"
               + '\n'.join(f"  ▸  {n}: {c:,}/week" for n, c in d['top_problem_sources'][:4])
               if d.get('top_problem_sources') else
               "\n\nEither thresholds are too sensitive or the estate is genuinely unstable - either way, "
               "a critical alert risks being lost in the noise.")
        ),
        'fix': lambda d: (
            (f"Start with the top source ({d['top_problem_sources'][0][0]}): raise its threshold or add a "
             "sustained-duration condition so it alerts on real saturation, not transient spikes. "
             if d.get('top_problem_sources') else
             'Tune thresholds and add frequency filters to suppress transient spikes. ')
            + 'Review the next sources the same way. Target: an actionable daily volume under 50.'
        ),
        'roadmap_action': 'Raise thresholds or add duration conditions on the noisiest alert rules',
        'roadmap_value':  'Daily problem volume the on-call team can actually work through',
    },
    {
        'key': 'slos',
        'trigger': lambda d: d.get('slo_count', 0) == 0,
        'priority': 'High Value',
        'slide_title': '{traces_per_day} Traces/Day Can Become Business SLOs Today',
        'card_title':  'The data to power SLOs is already flowing - reliability targets just need to be defined',
        'next_bullet': 'Define SLOs - {traces_per_day} traces/day and {services:,} services give you the data, just need targets set',
        'body': (
            'Dynatrace is capturing every transaction across {services:,} services, '
            '{traces_per_day} per day. That is the exact dataset SLOs are built on. No new instrumentation is needed.\n\n'
            'Right now the team cannot answer "are we meeting our commitments?" with data, and leadership '
            'has no report showing whether applications are performing to target. With SLOs defined, '
            'Dynatrace generates automatic burn-down alerts and status board reporting.\n\n'
            'SLOs can be live within hours. The foundation is already there.'
        ),
        'fix': lambda d: (
            (f"Start with the highest-traffic services: {_join(d['slo_candidates'], 3)} - availability and "
             "p95 latency targets on each. " if d.get('slo_candidates') else
             'Start with: (1) Availability SLO on key production applications (target: 99.9%), '
             '(2) Performance SLO on critical web request services (p95 < 500ms), '
             '(3) Error rate SLO on top 10 services by call volume. ')
            + (f"Recreate the {d['classic_slo_count']} classic SLO(s) as Gen3 SLOs and then delete the classic "
               "copy, so there is one source of truth." if d.get('classic_slo_count') else
               'Expand to the full service catalog using segments.')
        ),
        'roadmap_action': 'Define SLOs on key production applications and top services by call volume',
        'roadmap_value':  'Business-aligned reliability reporting and error budgets across {services:,} services',
    },
    {
        'key': 'workflows',
        'trigger': lambda d: d.get('workflow_count', 0) == 0,
        'priority': 'High Value',
        'slide_title': 'Add AutomationEngine on Top of Active Notifications',
        'card_title':  lambda d: (
            f"{d.get('notifications_count', 0)} classic notification channels, 0 workflows - AutomationEngine adds the layer that acts on problems"
            if d.get('notifications_count') else
            'No notification routing or workflows exist - problems are detected but nobody is told'),
        'next_bullet': 'Move notification routing onto AutomationEngine workflows',
        'body': lambda d: (
            (f"{d['customer']} routes problems through {d['notifications_count']} classic (Gen2) notification "
             "channels. Classic notifications can only forward a message - they cannot open a ticket, enrich the "
             "problem, or close it when it self-resolves.\n\n"
             if d.get('notifications_count') else
             f"{d['customer']} has no notification channels and no workflows: Davis detects problems, but "
             "nobody is told unless they are watching the UI.\n\n")
            + "AutomationEngine is the Gen3 layer: instead of an engineer reading the email, opening Dynatrace, "
            "creating a ticket, and assigning it by hand, a workflow does that automatically.\n\n"
            "Note: workflows require the AutomationEngine managed IAM policy bound to the admin group."
        ),
        'fix': (
            'Quick wins (live within one day): '
            '(1) Open ServiceNow or Jira ticket on any AVAILABILITY or ERROR problem, '
            '(2) Teams or Slack alert for problems affecting key production applications, '
            '(3) Auto-close problems that self-resolve within 5 minutes.'
        ),
        'dup_guard': lambda d: (
            'Disable each classic notification channel as the workflow that replaces it goes live - running both '
            'sends every alert twice.' if d.get('notifications_count') else ''),
        'roadmap_action': 'Create workflows: ticket creation, on-call routing, auto-close',
        'roadmap_value':  'Eliminates manual incident triage burden for on-call engineers',
    },
    {
        'key': 'database_extensions',
        # Skip when DB extensions already report - recommending them again is a duplicate.
        'trigger': lambda d: d.get('db_service_pct', 0) > 40 and not d.get('db_extensions_present'),
        'priority': 'High Value',
        'slide_title': 'Unlock Query-Level Visibility Across {db_services} Database Services',
        'card_title':  '{db_services} database services are already detected - extensions add the query depth that traces alone cannot',
        'next_bullet': 'Enable database extensions for {db_services} detected DB services - slow query and pool saturation visibility',
        'body': (
            '{db_services} of {services:,} services are database services - {db_service_pct}% of the service catalog. '
            'Dynatrace already knows they exist, tracks their call counts, and maps them in the topology. '
            'That discovery is the hard part.\n\n'
            'Database extensions build on top of that foundation to add:\n\n'
            '  ▸  Slow query detection with actual query text\n'
            '  ▸  Connection pool saturation alerts before they cascade\n'
            '  ▸  Wait statistics and index usage data\n\n'
            'Database performance is often the primary driver of end-to-end response time variability. '
            'This unlocks the next tier of root cause analysis.'
        ),
        'fix': (
            'Enable database extensions for the specific engines in use - SQL Server, Oracle, MySQL, PostgreSQL, '
            'and MongoDB extensions are all available. '
            'Cross-reference detected database services against known DB hostnames to identify which engines to prioritize first.'
        ),
        'roadmap_action': 'Enable database extensions for DB engines in use',
        'roadmap_value':  'Query-level visibility into the {db_service_pct}% database service tier ({db_services} services)',
    },
    {
        'key': 'rum_enablement',
        'trigger': lambda d: d.get('rum_apps_classic', 0) > 0 and not d.get('grail_rum_active', False),
        'priority': 'Phase 2',
        'slide_title': 'Enable New RUM Experience Across {rum_apps_classic} Configured Applications',
        'card_title':  '{rum_apps_classic} apps have classic RUM and JS beacons in place - the new Grail RUM experience is not yet active',
        'next_bullet': 'Enable new Grail RUM experience for {rum_apps_classic} apps - beacons deployed, platform not yet active',
        'body': (
            '{customer} has already done the instrumentation work: {rum_apps_classic} applications have classic RUM configured '
            'with JS beacons deployed. The agents are in place. What is not yet active is the new Grail RUM '
            'experience, which surfaces session replay, funnel analysis, and full DQL access to user event data.\n\n'
            'Zero user sessions are currently flowing to the new platform - user.events and user.sessions both '
            'return no records. Classic RUM data exists in isolation, separate from the rest of the Grail data set '
            'and not queryable alongside traces and logs.\n\n'
            'This is a configuration step, not a re-instrumentation. The JS beacon infrastructure is already deployed.'
        ),
        'fix': (
            'Enable the new RUM experience for each app in Applications & Microservices > Frontend. '
            'The JS beacon infrastructure is already deployed - this is a configuration step, not re-instrumentation. '
            'Review synthetic monitors for duplicates and QA or production mixing at the same time.'
        ),
        'roadmap_action': 'Enable new Grail RUM experience for {rum_apps_classic} configured apps; audit synthetic monitors',
        'roadmap_value':  'Full user session and funnel visibility queryable alongside traces and logs',
    },
    {
        'key': 'synthetic_cleanup',
        'trigger': lambda d: d.get('synthetic_monitors', 0) > 5 and d.get('rum_apps_classic', 0) == 0,
        'priority': 'Phase 2',
        'slide_title': 'Review {synthetic_monitors} Synthetic Monitors for Gaps and Duplicates',
        'card_title':  '{synthetic_monitors} monitors are active - an audit typically finds QA mixed with prod and coverage gaps on key flows',
        'next_bullet': 'Clean up {synthetic_monitors} synthetic monitors - remove duplicates, separate QA from prod',
        'body': (
            '{customer} has {synthetic_monitors} synthetic monitors running. Without a naming convention '
            'and environment separation, they tend to accumulate duplicates and mix QA with production in '
            'the same alerting baseline.\n\n'
            'Common patterns to look for:\n\n'
            '  ▸  Same endpoint monitored from multiple monitors with no clear ownership\n'
            '  ▸  QA monitors sharing alerting profiles with production monitors\n'
            '  ▸  Business-critical user flows with no synthetic coverage\n\n'
            'A one-hour audit typically results in fewer, better-targeted monitors with more reliable alerts.'
        ),
        'fix': (
            'Audit all {synthetic_monitors} monitors: (1) Delete or consolidate duplicates covering the same endpoint. '
            '(2) Separate QA monitors into a dedicated management zone with separate alerting thresholds. '
            '(3) Identify business-critical user flows with no synthetic coverage and create clickpath monitors for them.'
        ),
        'roadmap_action': 'Audit and consolidate {synthetic_monitors} synthetic monitors; separate QA from prod',
        'roadmap_value':  'Cleaner alerting baseline; synthetic coverage on critical user flows',
    },
    {
        'key': 'tagging_strategy',
        'trigger': lambda d: d.get('highlight_tagging', False),
        'priority': 'Phase 2',
        'slide_title': 'Establish a Consistent Tagging Strategy Across the Full Estate',
        'card_title':  'One tag taxonomy, applied everywhere - {cloud_providers_in_use} resources can inherit it automatically, the rest of the estate needs it applied directly',
        'next_bullet': 'Standardize tags estate-wide - {cloud_providers_in_use} can inherit automatically, on-prem needs the same taxonomy applied directly',
        'body': (
            '{customer} runs a meaningful footprint outside {cloud_providers_in_use} too. A tagging strategy '
            'that only covers cloud resources leaves the larger non-cloud estate untagged - defeating the '
            'point of having a taxonomy at all.\n\n'
            'For the {cloud_providers_in_use} portion, Dynatrace\'s cloud integration imports resource tags '
            'directly as Dynatrace tags at monitoring-configuration time - whatever convention exists there '
            'is inherited automatically, no re-tagging required.\n\n'
            'The taxonomy - environment, application/owner, business unit - has to be defined once and applied '
            'everywhere: inherited automatically for {cloud_providers_in_use}, applied via OneAgent host '
            'tagging rules for everything else.'
        ),
        'fix': (
            'Define one tag taxonomy up front: environment, application/owner, business unit. Apply it as '
            'native {cloud_providers_in_use} tags and enable automatic tag import in Settings > Cloud and '
            'Virtualization > {cloud_providers_in_use}. Apply the same taxonomy elsewhere via OneAgent host '
            'tagging rules so no part of the estate is left out.'
        ),
        'roadmap_action': 'Define one estate-wide tag taxonomy - auto-import for {cloud_providers_in_use}, tagging rules for everything else',
        'roadmap_value':  'Consistent environment/owner/business-unit metadata across on-prem and {cloud_providers_in_use} alike, not just the cloud portion of the estate',
    },
]

OPPORTUNITIES += [
    # ── Config hygiene: things that exist but silently don't work ──────────────
    {
        'key': 'alerting_profiles_broken',
        'trigger': lambda d: bool(d.get('alerting_profiles_no_rules') or d.get('alerting_profiles_test')
                                  or d.get('alerting_profiles_orphaned')),
        'priority': 'Config Fix',
        'slide_title': 'Alerting Profiles That Will Never Notify Anyone',
        # Count each list separately: a no-rules profile may or may not have a notification attached,
        # and the same profile can sit in both lists.
        'card_title': lambda d: '; '.join(filter(None, [
            (f"{_n(len(d['alerting_profiles_no_rules']), 'profile')} {'has' if len(d['alerting_profiles_no_rules']) == 1 else 'have'} "
             "no severity rules and can never fire" if d.get('alerting_profiles_no_rules') else ''),
            (f"{_n(len(d['alerting_profiles_test']), 'test profile')} "
             f"{'routes' if len(d['alerting_profiles_test']) == 1 else 'route'} to production channels"
             if d.get('alerting_profiles_test') else ''),
            (f"{_n(len(d['alerting_profiles_orphaned']), 'profile')} {'has' if len(d['alerting_profiles_orphaned']) == 1 else 'have'} "
             "no notification attached" if d.get('alerting_profiles_orphaned') else ''),
        ])),
        'next_bullet': 'Fix alerting profiles that can never fire',
        'body': lambda d: '\n'.join(filter(None, [
            (f"  ▸  No severity rules (never fires): {_join(d['alerting_profiles_no_rules'])}"
             if d.get('alerting_profiles_no_rules') else ''),
            (f"  ▸  Test profiles routing to production channels: {_join(d['alerting_profiles_test'])}"
             if d.get('alerting_profiles_test') else ''),
            (f"  ▸  Profiles with no notification attached: {_join(d['alerting_profiles_orphaned'])}"
             if d.get('alerting_profiles_orphaned') else ''),
            '',
            'Each of these looks configured in the UI, so the team assumes coverage that does not exist. The '
            'first sign of the gap is usually an outage nobody was paged for.',
        ])),
        'fix': (
            'Add the severity rules each profile was meant to carry (AVAILABILITY / ERRORS / CUSTOM_ALERT), delete '
            'test profiles from production, and either attach or remove orphaned profiles. Fold this into the '
            'workflow migration so the Gen3 workflow triggers are right first time.'
        ),
        'roadmap_action': 'Repair or remove alerting profiles that cannot fire',
        'roadmap_value': 'Alerts the team believes exist actually reach someone',
        'effort': '15 min', 'gen': 'Gen2',
    },
    {
        'key': 'mz_issues',
        'trigger': lambda d: bool(d.get('mz_issues')),
        'priority': 'Config Fix',
        'slide_title': 'Management Zone Rules Are Broken or Fragile',
        # mz_issues is a list of issue sentences, not zones (one sentence can cover many zones), so count issues.
        'card_title': lambda d: (f"{_n(len(d['mz_issues']), 'rule problem')} found across the "
                                 f"{d.get('mz_count', '?')} management zones"),
        'next_bullet': 'Fix broken management zone rules',
        'body': lambda d: '\n'.join(f"  ▸  {i}" for i in d['mz_issues'][:5]) + (
            '\n\nAlerting profiles and permissions scoped to these zones inherit the problem.'),
        'fix': (
            'Correct the rule conditions, and replace hard-coded entity IDs with name- or tag-based conditions. '
            'If zones are being migrated to Gen3 segments (see the upgrade path), fix the rule logic once there '
            'rather than in both places.'
        ),
        'roadmap_action': 'Correct broken MZ rule conditions; remove hard-coded entity IDs',
        'roadmap_value': 'Zone-scoped alerting and access see the entities they were built for',
        'effort': '30 min', 'gen': 'Gen2',
    },
    {
        'key': 'log_attribution',
        'trigger': lambda d: d.get('log_records_24h', 0) > 0 and d.get('log_unattributed_pct', 0) >= 50,
        'priority': 'Coverage',
        'slide_title': '{log_unattributed_pct}% of Logs Have No Host, Service, or Trace Attached',
        'card_title': '{log_records_24h:,} log records/day are stored, but {log_unattributed_pct}% cannot be reached from a host or service',
        'next_bullet': 'Link ingested logs to entities - {log_unattributed_pct}% are unattributed today',
        'body': lambda d: (
            f"{d['customer']} ingests {d.get('log_records_24h', 0):,} log records per day and {d.get('log_unattributed_pct')}% "
            "carry no dt.entity.host or dt.entity.service. Operators cannot pivot from a failing service into its "
            "logs, and log alerts cannot be scoped to a service.\n\n"
            + (f"Sources: {_join(d['log_sources'], 3)}." if d.get('log_sources') else '')
        ),
        'fix': (
            'Add OpenPipeline processing for the forwarded source that maps its resource fields (log group, '
            'container, function) to the matching entity. This is processing on logs already being ingested - '
            'no new volume.'
        ),
        'roadmap_action': 'Enrich forwarded logs with entity context in OpenPipeline',
        'roadmap_value': 'One-click host/service-to-log pivots during incidents',
        'effort': '2 hr', 'gen': 'Gen3',
    },
    {
        'key': 'host_naming',
        'trigger': lambda d: d.get('hosts_total', 0) > 0 and d.get('hosts_ip_named', 0) / d['hosts_total'] >= 0.5,
        'priority': 'Phase 2',
        'slide_title': '{hosts_ip_named} of {hosts_total} Hosts Are Named by IP Address',
        'card_title': 'Operators cannot tell what a host does without cross-referencing the cloud console',
        'next_bullet': 'Give {hosts_ip_named} IP-named hosts functional names',
        'body': lambda d: (
            f"{d['hosts_ip_named']} of {d['hosts_total']} hosts appear under their private DNS/IP name"
            + (", and none belong to a host group" if not d.get('host_groups') else '')
            + ". In problem cards and dashboards they are indistinguishable from each other."),
        'fix': (
            'Set host groups in the OneAgent deployment (e.g. one per ASG or role) and add host naming rules that '
            'use the cloud Name tag. Host groups also become a built-in segment dimension.'
        ),
        'roadmap_action': 'Host groups + naming rules from cloud Name tags',
        'roadmap_value': 'Problems and dashboards readable without the cloud console',
        'effort': '1 hr', 'gen': 'Gen3',
    },
    {
        'key': 'generic_service_names',
        'trigger': lambda d: bool(d.get('generic_services')),
        'priority': 'Phase 2',
        'slide_title': 'Rename Services Operators Cannot Identify',
        'card_title': lambda d: (f"{_n(len(d['generic_services']), 'service')} "
                                 f"{'has a generic name' if len(d['generic_services']) == 1 else 'have generic names'} "
                                 f"({_join(d['generic_services'], 3)})"),
        'next_bullet': 'Rename generic services so problems are actionable',
        'body': lambda d: (
            f"Services named {_join(d['generic_services'], 3)} show up in problems and service lists with no clue "
            "to which application they belong.\n\n"
            "Background-thread services (\"Requests executed in background threads of ...\") are a normal "
            "OneAgent pattern and are not included here."),
        'fix': 'Add service naming rules keyed on process group or deployment metadata for these services.',
        'roadmap_action': 'Service naming rules for generic service names',
        'roadmap_value': 'Problem cards name the application that is failing',
        'effort': '1 hr', 'gen': 'Gen3',
    },
    {
        'key': 'cpu_steady_high',
        'trigger': lambda d: d.get('hosts_cpu_ge60', 0) > 0,
        'priority': 'Phase 2',
        'slide_title': '{hosts_cpu_ge60} Hosts Run at a Sustained 60%+ CPU',
        'card_title': '{hosts_cpu_ge60} hosts averaged 60%+ CPU for two straight weeks - a capacity baseline, not a spike',
        'next_bullet': 'Set a capacity guardrail for {hosts_cpu_ge60} hosts running hot',
        'body': lambda d: (
            f"{d['hosts_cpu_ge60']} hosts averaged at least 60% CPU over the last 7 days (peak host "
            f"{d.get('cpu_max_avg', '?')}% avg, {d.get('cpu_max_p95', '?')}% p95), and the prior week looked the "
            "same. That is steady-state load with little headroom for a traffic burst."),
        'fix': (
            'Create a Gen3 Davis anomaly detector at a sustained 80% CPU for this host set, and review instance '
            'sizing / ASG scaling targets.'
        ),
        'roadmap_action': 'Sustained-CPU anomaly detector + right-sizing review',
        'roadmap_value': 'Warning before saturation rather than after',
        'effort': '30 min', 'gen': 'Gen3',
    },
    {
        'key': 'synthetic_absent',
        'trigger': lambda d: d.get('synthetic_monitors', -1) == 0,
        'priority': 'High Value',
        'slide_title': 'No Outside-In Monitoring of Customer-Facing Endpoints',
        'card_title': 'No synthetic monitors exist - an external outage is only visible once users report it',
        'next_bullet': 'Add HTTP monitors to external endpoints',
        'body': lambda d: (
            "A service can look healthy internally while being unreachable externally because of DNS, load "
            "balancer, or certificate issues."
            + (f"\n\nCandidate endpoints: {_join(d['external_endpoints'], 5)}." if d.get('external_endpoints') else '')),
        'fix': lambda d: (
            f"Start with HTTP monitors on the {len(d.get('external_endpoints') or []) or 'key'} external endpoints at "
            "5-minute frequency, then add browser clickpaths for login."),
        'roadmap_action': 'HTTP monitors on external endpoints',
        'roadmap_value': 'Outside-in availability independent of internal telemetry',
        'effort': '2 hr', 'gen': 'Gen3',
    },
    {
        'key': 'retention_review',
        'trigger': lambda d: d.get('log_retention_days', 999) <= 35 and not d.get('retention_confirmed'),
        'priority': 'Phase 2',
        'slide_title': 'Confirm Log Retention Matches Compliance Needs',
        'card_title': 'Logs are on the default {log_retention_days}-day bucket - confirm that meets audit and RCA needs',
        'next_bullet': 'Confirm log retention policy',
        'body': (
            'All logs land in the default {log_retention_days}-day bucket. That is fine for operations, but audit '
            'or incident-review needs often run longer.\n\n'
            'Reviewing the setting takes minutes, and a longer retention period applies only to the bucket that needs it.'
        ),
        'fix': 'Agree retention per log type with the compliance owner, then create a dedicated bucket only for the logs that need it.',
        'roadmap_action': 'Agree log retention per data type; dedicated bucket if needed',
        'roadmap_value': 'Retention set by requirement, not by default',
        'effort': '1 hr', 'gen': 'Gen3',
    },
]

# Effort and platform-generation label for the original library entries.
# 'gen' is Gen3 (improve what's on the platform), Gen2 (classic feature), or Both.
_OPP_META = {
    'oneagent_coverage':  ('2 hr',     'Gen3'),
    'log_enablement':     ('2 hr',     'Gen3'),
    'log_to_trace':       ('1 hr',     'Gen3'),
    'cloud_coverage_gaps':('1 day',    'Gen3'),
    'vmware_coverage':    ('2 hr',     'Gen3'),
    'vmware_data_gap':    ('2 hr',     'Gen3'),
    'alert_tuning':       ('2 hr',     'Gen3'),
    'slos':               ('1 hr',     'Gen3'),
    'workflows':          ('3 hr',     'Gen3'),
    'database_extensions':('1 day',    'Gen3'),
    'rum_enablement':     ('2 hr',     'Upgrade'),
    'synthetic_cleanup':  ('1 hr',     'Gen3'),
    'tagging_strategy':   ('2 hr',     'Gen3'),
}
for _o in OPPORTUNITIES:
    if _o['key'] in _OPP_META:
        _o.setdefault('effort', _OPP_META[_o['key']][0])
        _o.setdefault('gen', _OPP_META[_o['key']][1])

# A platform_matrix row for the same area supersedes the generic library slide, so
# the deck never carries two slides for one migration.
_MATRIX_SUPERSEDES = {
    'workflows': 'Problem notifications',
    'slos': 'SLOs',
    'rum_enablement': 'Real User Monitoring',
    'tagging_strategy': 'Management zones',
}

TIER_ORDER = ['Coverage', 'Anomaly', 'Config Fix', 'Upgrade', 'Start Here', 'High Value', 'Phase 2']
MAX_ANOMALY_FINDINGS = 6
SEVERITY_ORDER = {'high': 0, 'medium': 1, 'low': 2}

def _matrix_opportunities(data):
    """One Upgrade-tier slide per platform_matrix row still on Gen2 (or running both).
    Rows flagged duplicate=True already have a Gen3 equivalent doing the same job, so the
    step is 'consolidate onto Gen3 and retire the classic copy' - never 'add another'."""
    opps = []
    for r in data.get('platform_matrix', []):
        if r.get('status') not in ('Gen2', 'Both'):
            continue
        consolidate = r.get('status') == 'Both' or r.get('duplicate')
        verb = 'Consolidate' if consolidate else 'Upgrade'
        opps.append({
            'key': f"upgrade_{r['area']}",
            'trigger': lambda d: True,
            'priority': 'Upgrade',
            'slide_title': r.get('title', f"{r['area']}: {r['gen2']} to {r['gen3']}"),
            'card_title': r.get('headline', f"{r['area']} still runs on {r['gen2']}"),
            'next_bullet': f"{verb} {r['area']} onto {r['gen3']}",
            'label': r.get('label', f"{verb} {r['area']}"),
            'body': r.get('detail', ''),
            'fix': r.get('next_step', ''),
            'dup_guard': r.get('duplication_check', ''),
            'roadmap_action': r.get('action', f"{verb} {r['area']} to {r['gen3']}"),
            'roadmap_value': r.get('value', f"{r['area']} on the Gen3 platform"),
            'effort': r.get('effort', '?'),
            'gen': 'Both' if consolidate else 'Upgrade',
        })
    return opps

def _custom_opportunities(data):
    """Tenant-specific findings the library has no trigger for (an oversized log source, a duplicated
    workflow, a misrouted exporter). Same shape as a platform_matrix row plus 'tier'."""
    opps = []
    for c in data.get('custom_findings', []):
        opps.append({
            'key': c['key'], 'trigger': lambda d: True,
            'priority': c.get('tier', 'Start Here') if c.get('tier') in TIER_ORDER else 'Start Here',
            'slide_title': c['title'], 'card_title': c.get('headline', c['title']),
            'next_bullet': c.get('label', c['title']), 'label': c.get('label', c['title']),
            'body': c.get('detail', ''), 'fix': c.get('next_step', ''),
            'dup_guard': c.get('duplication_check', ''),
            'roadmap_action': c.get('action', c['title']), 'roadmap_value': c.get('value', ''),
            'effort': c.get('effort', '?'),
            'gen': c.get('gen', 'Gen3'),
            **({'phase': c['phase']} if 'phase' in c else {}),
        })
    return opps

def _anomaly_opportunities(data):
    """Turn data['anomalies'] (list of {scope, entity, metric, kind, summary,
    recommendation, severity?}) into opportunity-shaped dicts at the Anomaly tier,
    capped and sorted by severity so the deck can't be overrun by noisy baselines."""
    anomalies = sorted(
        data.get('anomalies', []),
        key=lambda a: SEVERITY_ORDER.get(a.get('severity', 'medium'), 1),
    )[:MAX_ANOMALY_FINDINGS]
    opps = []
    for a in anomalies:
        label = f"{a['scope'].capitalize()} anomaly: {a['entity']}"
        opps.append({
            'key': f"anomaly_{a['entity']}_{a['metric']}",
            'trigger': lambda d: True,
            'priority': 'Anomaly',
            'slide_title': a.get('title', label),
            'card_title':  a['summary'],
            'next_bullet': f"Investigate {a['entity']} - {a['summary']}",
            'label': a.get('label', f"Investigate {a['entity']}"),
            'body': a.get('detail', ''),
            'fix': a['recommendation'],
            'roadmap_action': f"Investigate {a['metric']} anomaly on {a['entity']}",
            'roadmap_value': a.get('value', 'Root cause found before it turns into an outage'),
            'effort': a.get('effort', '2 hr'), 'gen': 'Gen3',
            **({'phase': 1} if a.get('severity') == 'high' else {}),
        })
    return opps

# ── HELPERS ───────────────────────────────────────────────────────────────────
def asset(name):
    return os.path.join(ASSETS, name)

COVER_ART = os.path.join(SKILL_DIR, 'assets', 'cover_art.png')

def _real_asset(path):
    """The pptx-skill assets are Git LFS files; a clone without LFS leaves ~130-byte
    pointer stubs in their place, which open as 'not a zip file' / broken images."""
    return os.path.exists(path) and os.path.getsize(path) > 1024

def _ensure_template(template=None):
    """Returns the deck to build on. Order: --template (or DT_TEMPLATE env var) pointing
    at any .pptx/.potx on the 2026 corporate master, then the cached fixed template,
    then the pptx-skill's DT_template.potx."""
    template = template or os.environ.get('DT_TEMPLATE')
    if template and template.lower().endswith('.pptx'):
        return template
    if not template and os.path.exists(TMPL_FIXED):
        return TMPL_FIXED
    potx = template or asset('DT_template.potx')
    if not _real_asset(potx):
        sys.exit(f'ERROR: {potx} is missing or a Git LFS pointer stub. Run `git lfs pull` in the skills '
                 'repo, or pass --template <any deck on the DT 2026 corporate master>.')
    # zipfile instead of shelling out to unzip/zip - Git Bash on Windows ships
    # unzip but not zip, so the subprocess version failed there.
    with zipfile.ZipFile(potx) as src, zipfile.ZipFile(TMPL_FIXED, 'w', zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            buf = src.read(item.filename)
            if item.filename == '[Content_Types].xml':
                buf = buf.decode('utf-8').replace(
                    'presentationml.template.main+xml',
                    'presentationml.presentation.main+xml').encode('utf-8')
            dst.writestr(item, buf)
    return TMPL_FIXED

# Layouts are looked up by name, not index - corporate decks built on the same master
# reorder and add layouts, so fixed indices land on the wrong slide type.
LAYOUTS = {
    'cover':   (['1_Title Slide', 'Title Slide'], 0),
    'content': (['Blank_graphic', 'Dark: blank slide', '1_Blank', 'Blank'], 61),
    'close':   (['Thank you slide'], 63),
}

def layout(prs, kind):
    names, fallback = LAYOUTS[kind]
    by_name = {l.name: l for l in prs.slide_layouts}
    for n in names:
        if n in by_name:
            return by_name[n]
    return prs.slide_layouts[min(fallback, len(prs.slide_layouts) - 1)]

def _send_to_back(slide, shape):
    slide.shapes._spTree.remove(shape._element)
    slide.shapes._spTree.insert(2, shape._element)

def _clear_placeholders(slide):
    for ph in list(slide.placeholders):
        ph._element.getparent().remove(ph._element)

def white_bg(slide):
    """Full-bleed white rectangle, the same way the reference deck hides the layout artwork."""
    r = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Emu(12192000), Emu(6858000))
    r.fill.solid(); r.fill.fore_color.rgb = WHITE; r.line.fill.background(); r.shadow.inherit = False
    _send_to_back(slide, r)

def cover_bg(slide):
    slide.background.fill.solid(); slide.background.fill.fore_color.rgb = COVER_BG
    if _real_asset(COVER_ART):
        pic = slide.shapes.add_picture(COVER_ART, 0, 0, width=Emu(12192000), height=Emu(6858000))
        _send_to_back(slide, pic)

def add_text(slide, text, x, y, w, h, size=14, bold=False, color=NAVY,
             align=PP_ALIGN.LEFT, italic=False, anchor=MSO_ANCHOR.TOP):
    """Text box with zero insets. Each '\n' becomes its own paragraph so blank lines survive."""
    txb = slide.shapes.add_textbox(x, y, w, h)
    tf = txb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    for i, line in enumerate(str(text).split('\n')):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        run = p.add_run()
        run.text = line
        run.font.size = Pt(size); run.font.bold = bold; run.font.italic = italic
        run.font.color.rgb = color; run.font.name = FONT
    return txb

def card(slide, x, y, w, h, accent=None, fill=WHITE, radius_in=0.06):
    """Rounded card with the reference deck's fixed ~0.06in corner, whatever the card size."""
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    box.adjustments[0] = min(0.5, Inches(radius_in) / min(w, h))
    box.fill.solid(); box.fill.fore_color.rgb = fill
    box.line.color.rgb = BORDER; box.line.width = Pt(0.75)
    box.shadow.inherit = False
    if accent is not None:
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, Inches(0.07), h)
        bar.fill.solid(); bar.fill.fore_color.rgb = accent; bar.line.fill.background()
        bar.shadow.inherit = False
    return box

def pill(slide, label, color, x, y, w=Inches(1.45), h=Inches(0.36)):
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    box.adjustments[0] = 0.5
    box.fill.solid(); box.fill.fore_color.rgb = color; box.line.fill.background()
    box.shadow.inherit = False
    tf = box.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    run = p.add_run(); run.text = label
    run.font.size = Pt(9.5); run.font.bold = True
    run.font.color.rgb = WHITE; run.font.name = FONT

def slide_title(slide, text, subtitle=None):
    size = 26 if len(text) <= 58 else 22 if len(text) <= 80 else 19
    add_text(slide, text, Inches(0.45), Inches(0.62), Inches(12.1), Inches(0.5),
             size=size, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    if subtitle:
        add_text(slide, subtitle, Inches(0.45), Inches(1.18), Inches(12.1), Inches(0.35),
                 size=13.5, color=GREY, anchor=MSO_ANCHOR.MIDDLE)

def page_number(slide, n):
    add_text(slide, str(n), Inches(12.35), Inches(7.05), Inches(0.5), Inches(0.25),
             size=8, color=GREY, align=PP_ALIGN.RIGHT)

def stat_card(slide, big, label, x, y, accent):
    w, h = Inches(2.85), Inches(1.9)
    card(slide, x, y, w, h, accent=accent)
    add_text(slide, big, x + Inches(0.3), y + Inches(0.3), w - Inches(0.45), Inches(0.75),
             size=36, bold=True, color=accent, anchor=MSO_ANCHOR.MIDDLE)
    add_text(slide, label, x + Inches(0.3), y + Inches(1.15), w - Inches(0.45), Inches(0.6),
             size=12.5, color=GREY)

def _clip(text, n):
    """Shorten to n characters at a sentence end if one fits, else at a word, so a card never overflows."""
    text = ' '.join(str(text or '').split())
    if len(text) <= n:
        return text
    cut = text[:n]
    for stop in ('. ', '; '):
        k = cut.rfind(stop)
        if k >= n * 0.5:
            return cut[:k + 1]
    return cut.rsplit(' ', 1)[0].rstrip(',;:-') + '...'

def _text_lines(text, size, width_in):
    """Estimated wrapped line count for Arial at `size` pt in a box `width_in` inches wide."""
    per_line = max(8, int(width_in / (0.40 * size / 72)))
    return sum(max(1, -(-len(seg) // per_line)) for seg in str(text).split('\n'))

def finding_panel(slide, f, x, y, w, h, rows, title='Priority finding', sizes=(15, 14, 13, 12)):
    """The reference deck's example-finding panel, laid out for reading: tier pill, then each section as a
    small coloured label over full-width body text with a divider between sections, and a two-part footer.
    rows: [(label, text, ...)]. Body size steps down from 15pt until every section fits the panel."""
    accent = TIER_COLOR.get(f['tier'], BLUE)
    inner_x, inner_w = x + Inches(0.4), w - Inches(0.8)
    inner_in = inner_w / 914400
    top, foot = 0.95, 0.75                       # header block above, footer block below (inches)
    avail = h / 914400 - top - foot
    def need(sz):
        line_h = sz * 1.22 / 72
        return sum(0.27 + _text_lines(r[1], sz, inner_in) * line_h for r in rows) + 0.2 * (len(rows) - 1) + 0.25
    size = next((s for s in sizes if need(s) <= avail), sizes[-1])
    if need(size) > avail:
        print(f'WARNING: finding_panel text may overflow at {size}pt: {f["label"][:50]!r}', file=sys.stderr)

    card(slide, x, y, w, h, fill=PANEL)
    add_text(slide, title, inner_x, y + Inches(0.3), Inches(4), Inches(0.35), size=18, bold=True,
             anchor=MSO_ANCHOR.MIDDLE)
    pill(slide, f['tier'].upper(), accent, x + w - Inches(1.85), y + Inches(0.3))
    ry = y + Inches(top)
    line_h = size * 1.22 / 72
    for i, r in enumerate(rows):
        label, text = r[0], r[1]
        add_text(slide, label.upper(), inner_x, ry, inner_w, Inches(0.22), size=10.5, bold=True, color=accent)
        body_h = _text_lines(text, size, inner_in) * line_h
        add_text(slide, text, inner_x, ry + Inches(0.27), inner_w, Inches(body_h), size=size)
        ry += Inches(0.27 + body_h)
        if i < len(rows) - 1:
            ry += Inches(0.1)
            d = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, inner_x, ry, inner_x + inner_w, ry)
            d.line.color.rgb = BORDER; d.line.width = Pt(0.75)
            ry += Inches(0.1)
    line_y = y + h - Inches(foot)
    ln = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, inner_x, line_y, inner_x + inner_w, line_y)
    ln.line.color.rgb = BORDER; ln.line.width = Pt(1)
    ph = PHASES[f['phase']]
    add_text(slide, f"Effort: {f['effort']}  ·  {GEN_LABEL.get(f['gen'], f['gen'])}",
             inner_x, line_y + Inches(0.22), Emu(int(inner_w * 0.62)), Inches(0.3), size=12, color=GREY)
    add_text(slide, f"{ph[0].split(' - ')[0]}  ·  {ph[1]}", inner_x + Emu(int(inner_w * 0.62)), line_y + Inches(0.22),
             Emu(int(inner_w * 0.38)), Inches(0.3), size=12, color=GREY, align=PP_ALIGN.RIGHT)

# ── SCORING + BUILD ───────────────────────────────────────────────────────────
PHASE_FOR_TIER = {
    'Coverage': 'Week 1', 'Anomaly': 'Week 1',
    'Start Here': 'Weeks 2-4', 'High Value': 'Weeks 2-4',
    'Phase 2': 'This Quarter',
}

PHASE_FOR_TIER.update({'Config Fix': 'Week 1', 'Upgrade': 'Weeks 2-6'})

def score(data):
    matrix_areas = {r.get('area') for r in data.get('platform_matrix', [])
                    if r.get('status') in ('Gen2', 'Both')}
    library = [o for o in OPPORTUNITIES
               if _MATRIX_SUPERSEDES.get(o['key']) not in matrix_areas and o['trigger'](data)]
    active = (library + _anomaly_opportunities(data) + _matrix_opportunities(data)
              + _custom_opportunities(data))
    # SE overrides per finding key: shorter slide labels and realistic effort for this tenant.
    active = [dict(o, **{k: data[f'{k}_overrides'][o['key']] for k in ('label', 'effort')
                         if o['key'] in data.get(f'{k}_overrides', {})}) for o in active]
    active = sorted(active, key=lambda o: TIER_ORDER.index(o['priority']))
    # SE-pinned priorities (data['top_priorities'], list of keys) lead, in that order.
    pins = {k: i for i, k in enumerate(data.get('top_priorities', []))}
    return sorted(active, key=lambda o: pins.get(o['key'], len(pins)))

def fmt(s, data):
    """Text fields are either format strings or callables taking data (used where
    the narrative has to branch on what the tenant actually has)."""
    if callable(s):
        return s(data)
    try:
        return s.format(**data)
    except (KeyError, ValueError) as e:
        print(f'WARNING: fmt() failed on {s[:60]!r} ({e}) - rendering unformatted. '
              f'Likely a stray {{ or }} in a model-written anomaly string.', file=sys.stderr)
        return s


def _auto_stat_cards(data):
    cards = [
        (str(data.get('hosts', 0)),                   'Hosts\nMonitored by OneAgent'),
        (f"{data.get('services', 0):,}",              'Services\nAuto-Discovered'),
        (str(data.get('traces_per_day', '?')),        'Service Requests\nPer Day'),
    ]
    if data.get('rum_apps_classic', 0) > 0 and not data.get('grail_rum_active', False):
        cards.append((str(data['rum_apps_classic']), 'Classic RUM Apps\n(Not Yet on Grail)'))
    elif data.get('synthetic_monitors', 0) > 0:
        cards.append((str(data['synthetic_monitors']), 'Synthetic Monitors\nConfigured'))
    else:
        cards.append((f"{data.get('problems_per_week', 0):,}", 'Problems\nLast 7 Days'))
    return cards

def _estate_stats(data):
    """Full-estate OneAgent coverage: folds in cloud/VMware hosts discovered but not
    yet OneAgent-monitored, so the % reflects the whole estate, not just agented hosts."""
    oneagent_hosts = data.get('hosts_fullstack', 0) + data.get('hosts_infra', 0)
    cloud_only     = data.get('cloud_hosts_without_oneagent', 0)
    vmware_only    = data.get('vmware_hosts_without_oneagent', 0)
    total          = oneagent_hosts + cloud_only + vmware_only
    coverage_pct   = round((oneagent_hosts / total) * 100, 1) if total else 0.0
    return {
        'oneagent_hosts': oneagent_hosts,
        'cloud_only': cloud_only,
        'vmware_only': vmware_only,
        'total': total,
        'coverage_pct': coverage_pct,
    }

# ── PHASING (lift x complexity) ───────────────────────────────────────────────
PHASES = {
    1: ('Phase 1 - Quick Wins',        'Weeks 1-2',    'Low'),
    2: ('Phase 2 - Core Improvements', 'Weeks 3-6',    'Medium'),
    3: ('Phase 3 - Strategic',         'This quarter', 'High'),
}
EFFORT_TIERS = ['Low Effort', 'Medium Effort', 'High Effort']
EFFORT_COLOR = {'Low Effort': BLUE, 'Medium Effort': PURPLE, 'High Effort': MAGENTA}
EFFORT_SUB   = {'Low Effort': 'an hour or less', 'Medium Effort': 'a few hours to a day',
                'High Effort': 'multi-day project'}

def _hours(effort):
    """'15 min' / '2 hr' / '1-2 days' -> rough hours (upper bound) for phasing."""
    e = str(effort or '').lower().replace('+', '')
    num = [float(x) for x in e.replace('-', ' ').split() if x.replace('.', '').isdigit()]
    n = max(num) if num else 4
    return n / 60 if 'min' in e else n * 8 if 'day' in e else n * 40 if 'week' in e else n

def _phase(o):
    if 'phase' in o:
        return o['phase']
    h = _hours(o.get('effort'))
    return 1 if h <= 1 else 2 if h <= 8 else 3

def _effort_tier(o):
    """Deck-facing grouping by lift: <=1 hr Low, <=1 day Medium, longer High."""
    h = _hours(o.get('effort'))
    return 'Low Effort' if h <= 1 else 'Medium Effort' if h <= 8 else 'High Effort'

def _label(o, data):
    if o.get('label'):
        return fmt(o['label'], data)
    return fmt(o['next_bullet'], data).split(' - ')[0]

def plan(data):
    """Rendered findings shared by the deck and the written report."""
    out = []
    for o in score(data):
        out.append({
            'key': o['key'], 'tier': o['priority'], 'label': _label(o, data),
            'title': fmt(o['slide_title'], data), 'headline': fmt(o['card_title'], data),
            'body': fmt(o['body'], data), 'fix': fmt(o['fix'], data),
            'dup_guard': fmt(o.get('dup_guard', ''), data),
            'action': fmt(o['roadmap_action'], data), 'value': fmt(o['roadmap_value'], data),
            'effort_tier': _effort_tier(o),
            'effort': o.get('effort', '?'),
            'gen': o.get('gen', 'Gen3'), 'phase': _phase(o),
        })
    return out

def _exec_overview_bullets(data, active, est):
    """Four short headline bullets for the Executive Overview slide."""
    phase1 = sum(1 for o in active if _phase(o) == 1)
    quick = sum(1 for o in active if _effort_tier(o) == 'Low Effort')
    bullets = [
        data.get('exec_coverage_bullet') or
        f"OneAgent covers {est['coverage_pct']}% of the estate "
        f"({est['oneagent_hosts']} of {est['total']} running hosts)",
        f"{len(active)} findings, {quick} of them deliverable in an hour or less",
        f"{phase1} can be closed in the first two weeks",
    ]
    bullets.append(f"Top priority: {_label(active[0], data)}" if active
                   else "No material gaps identified in this review.")
    return bullets

def panel(slide, x, y, w, h, header, color, big, items, more=0, sub=''):
    """Column card: accent bar, header, optional big number + subline, item list.
    Items go in ONE text box as paragraphs so PowerPoint does the wrapping - separate
    boxes per item overlapped whenever a label wrapped to a second line."""
    card(slide, x, y, w, h, accent=color)
    add_text(slide, header, x + Inches(0.3), y + Inches(0.22), w - Inches(0.5), Inches(0.3),
             size=17, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    ty = y + Inches(0.75)
    if big is not None:
        band = card(slide, x + Inches(0.3), ty - Inches(0.05), w - Inches(0.55), Inches(0.75), fill=LIGHT)
        band.line.fill.background()
        add_text(slide, big, x + Inches(0.5), ty, Inches(0.9), Inches(0.65),
                 size=34, bold=True, color=color, anchor=MSO_ANCHOR.MIDDLE)
        if sub:
            add_text(slide, sub, x + Inches(1.45), ty, w - Inches(1.85), Inches(0.65),
                     size=12.5, color=GREY, anchor=MSO_ANCHOR.MIDDLE)
        ty += Inches(0.95)
    lines = list(items) or ['None identified']
    txb = slide.shapes.add_textbox(x + Inches(0.3), ty, w - Inches(0.5), y + h - ty - Inches(0.15))
    tf = txb.text_frame; tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, item in enumerate(lines + ([f'+ {more} more in the full report'] if more else [])):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(8)
        extra = bool(more and i == len(lines))
        muted = extra or not items
        run = p.add_run(); run.text = item if muted else f'•  {item}'; run.font.name = FONT
        run.font.size = Pt(12 if extra else 13)
        run.font.italic = muted
        run.font.color.rgb = GREY if muted else NAVY

def _panel_height(items, width_in, has_big, more=0):
    """Inches a panel needs for its content, so cards hug their text instead of floating in white."""
    per_line = max(10, int((width_in - 0.5) / 0.093))
    body = sum(0.23 * (-(-len(i) // per_line)) + 0.11 for i in (items or ['None identified']))
    return max(3.2, 0.75 + (0.95 if has_big else 0) + body + (0.3 if more else 0) + 0.25)

def strip(slide, text, y):
    """Full-width light grey takeaway band, like the reference deck's closing line."""
    card(slide, Inches(0.55), y, Inches(12.2), Inches(0.7), fill=LIGHT)
    add_text(slide, text, Inches(0.85), y, Inches(11.6), Inches(0.7), size=15, bold=True, anchor=MSO_ANCHOR.MIDDLE)

def _three_panels(slide, groups, max_items=5, footer=None):
    """groups: [(header, color, big, sub, [labels])] -> three side-by-side panels, equal height."""
    shown = [(g, g[4][:max_items], max(0, len(g[4]) - max_items)) for g in groups]
    h = max(_panel_height(it, 3.9, g[2] is not None, more) for g, it, more in shown)
    xs = {1: [4.7], 2: [2.64, 6.79], 3: [0.55, 4.7, 8.85]}[len(shown)]   # centre when fewer than three panels
    for ((header, color, big, sub, _), items, more), x in zip(shown, [Inches(v) for v in xs]):
        panel(slide, x, Inches(1.8), Inches(3.9), Inches(h), header, color, big, items, more=more, sub=sub)
    if footer:
        strip(slide, footer, Inches(1.8 + h + 0.3))

def _content_slide(prs, title, subtitle=None):
    s = prs.slides.add_slide(layout(prs, 'content'))
    _clear_placeholders(s)
    white_bg(s)
    slide_title(s, title, subtitle)
    page_number(s, len(prs.slides))
    return s

def load_data(paths):
    """Merge facts.json (collect.py) with overrides.json (model judgment); later files win."""
    data = {}
    for path in paths:
        with open(path, encoding='utf-8') as f:
            data.update(json.load(f))
    return data

def build(data, customer, tenant, output, detail=False, report_name=None, template=None):
    tmpl = _ensure_template(template)
    data['customer'] = customer

    prs   = Presentation(tmpl)
    TODAY = datetime.date.today().strftime('%B %d, %Y')

    sldIdLst = prs.slides._sldIdLst
    for sldId in list(sldIdLst):
        rId = sldId.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        prs.part.drop_rel(rId)
        sldIdLst.remove(sldId)

    active   = score(data)
    findings = plan(data)
    est      = _estate_stats(data)
    accents  = [BLUE, PURPLE, MAGENTA, ROYAL]

    # Cover: full-bleed artwork (carries the Dynatrace logo), title and tagline as in the reference deck
    s = prs.slides.add_slide(layout(prs, 'cover'))
    _clear_placeholders(s)
    cover_bg(s)
    add_text(s, 'Observability Gap Analysis', Inches(0.625), Inches(2.48), Inches(9), Inches(0.8),
             size=34, bold=True, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
    add_text(s, 'Find the blind spots. Prioritize what matters. Build the action plan.',
             Inches(0.625), Inches(3.55), Inches(9), Inches(0.45), size=18, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
    add_text(s, f'{customer}  ·  Value Roadmap  ·  {TODAY}', Inches(0.625), Inches(4.3), Inches(9), Inches(0.4),
             size=14, color=BLUE, anchor=MSO_ANCHOR.MIDDLE)

    # Executive overview: four cards, accent bar + heading + one-line fact (reference "Why" slide)
    s = _content_slide(prs, 'Executive overview',
                       'What Dynatrace sees today, what to close first, and how much effort it takes.')
    heads = ['Coverage today', 'Findings and effort', 'First two weeks', 'Top priority']
    bullets = _exec_overview_bullets(data, active, est)
    bullets[3] = bullets[3].replace('Top priority: ', '', 1)
    for i, (head, body) in enumerate(zip(heads, bullets)):
        y = Inches(1.8) + Inches(1.1) * i
        card(s, Inches(0.55), y, Inches(12.2), Inches(0.92), accent=accents[i])
        add_text(s, head, Inches(0.85), y, Inches(3.0), Inches(0.92), size=17, bold=True, anchor=MSO_ANCHOR.MIDDLE)
        add_text(s, body, Inches(4.0), y, Inches(8.4), Inches(0.92), size=15, anchor=MSO_ANCHOR.MIDDLE)
    add_text(s, f'Outcome: a prioritized, evidence-based plan for {customer}', Inches(0.55), Inches(6.35),
             Inches(12.2), Inches(0.35), size=15, bold=True)

    # Current state
    s = _content_slide(prs, 'Current state at a glance', 'The estate Dynatrace is monitoring right now.')
    cards = data.get('stat_cards') or _auto_stat_cards(data)
    for (big, label), x, accent in zip(cards[:4], [Inches(0.55), Inches(3.67), Inches(6.79), Inches(9.91)],
                                       [BLUE, ROYAL, PURPLE, MAGENTA]):
        stat_card(s, big, label, x, Inches(1.9), accent)
    # Second row: configuration the estate carries today (grey tiles), from whatever the data holds
    def _compact(n):
        return f'{n / 1e9:.1f}B' if n >= 1e9 else f'{n / 1e6:.1f}M' if n >= 1e6 else f'{n / 1e3:.0f}K' if n >= 1e4 else f'{n:,}'
    tile_src = [('log_records_24h', 'Log Records\nPer Day'), ('alerting_profiles', 'Alerting\nProfiles'),
                ('notifications_count', 'Classic\nNotifications'), ('mz_count', 'Management\nZones'),
                ('synthetic_monitors', 'Synthetic\nMonitors'), ('workflow_count', 'Workflows'),
                ('slo_count', 'SLOs Defined')]
    tiles = [(_compact(int(data[k])), label) for k, label in tile_src
             if isinstance(data.get(k), (int, float))][:4]
    for (big, label), x in zip(tiles, [Inches(0.55), Inches(3.67), Inches(6.79), Inches(9.91)]):
        card(s, x, Inches(3.95), Inches(2.85), Inches(1.4), fill=LIGHT).line.fill.background()
        add_text(s, big, x + Inches(0.3), Inches(4.07), Inches(2.4), Inches(0.5), size=26, bold=True,
                 anchor=MSO_ANCHOR.MIDDLE)
        add_text(s, label, x + Inches(0.3), Inches(4.65), Inches(2.4), Inches(0.55), size=12, color=GREY)
    matrix = data.get('platform_matrix', [])
    if matrix:
        g3 = sum(1 for r in matrix if r.get('status') == 'Gen3')
        g2 = sum(1 for r in matrix if r.get('status') in ('Gen2', 'Both'))
        strip(s, f'{g3} capability areas run on Gen3 today. {g2} still use classic (Gen2) features.', Inches(5.65))

    # Gen2 / Gen3 platform view
    if matrix:
        s = _content_slide(prs, 'Platform position: Gen2 and Gen3', 'Where each capability runs today.')
        gen3 = [r['area'] for r in matrix if r.get('status') == 'Gen3']
        up   = [f"{r['area']} to {r['gen3']}" for r in matrix if r.get('status') in ('Gen2', 'Both')]
        cols = [('On Gen3 today', BLUE, gen3[:7], max(0, len(gen3) - 7)),
                ('Upgrade path from Gen2', MAGENTA, up[:7], max(0, len(up) - 7))]
        h = max(_panel_height(it, 6.0, False, more) for _, _, it, more in cols)
        for (header, color, items, more), x in zip(cols, [Inches(0.55), Inches(6.78)]):
            panel(s, x, Inches(1.8), Inches(6.0), Inches(h), header, color, None, items, more=more)
        strip(s, f'{len(gen3)} areas on Gen3  ·  {len(up)} upgrade paths  ·  each upgrade replaces the classic '
                 'feature rather than running alongside it', Inches(1.8 + h + 0.3))

    # Top priorities
    s = _content_slide(prs, 'Top priorities', 'Ordered by where the evidence says to start.')
    for i, f in enumerate(findings[:5]):
        y = Inches(1.75) + Inches(0.97) * i
        color = EFFORT_COLOR[f['effort_tier']]
        card(s, Inches(0.55), y, Inches(12.2), Inches(0.82), accent=color)
        add_text(s, str(i + 1), Inches(0.85), y, Inches(0.4), Inches(0.82), size=22, bold=True, color=color,
                 anchor=MSO_ANCHOR.MIDDLE)
        add_text(s, f['label'], Inches(1.4), y, Inches(7.6), Inches(0.82), size=16, bold=True, anchor=MSO_ANCHOR.MIDDLE)
        pill(s, f['effort_tier'].upper(), color, Inches(9.35), y + Inches(0.23))
        add_text(s, f"Effort: {f['effort']}", Inches(11.0), y, Inches(1.6), Inches(0.82), size=12.5, color=GREY,
                 anchor=MSO_ANCHOR.MIDDLE)

    # Where to start: the first finding in detail (reference "example finding" slide)
    if findings:
        s = _content_slide(prs, 'Where to start', 'The first finding in detail, with the next two in line.')
        for i, f in enumerate(findings[:3]):
            y = Inches(1.7) + Inches(1.75) * i
            card(s, Inches(0.55), y, Inches(5.1), Inches(1.4), accent=accents[i])
            add_text(s, _clip(f['label'], 46), Inches(0.85), y + Inches(0.3), Inches(4.65), Inches(0.35), size=15, bold=True)
            add_text(s, f"{f['effort_tier']}  ·  {f['effort']}  ·  {PHASES[f['phase']][0].split(' - ')[0]}",
                     Inches(0.85), y + Inches(0.8), Inches(4.65), Inches(0.3), size=12.5, color=GREY)
        top = findings[0]
        finding_panel(s, top, Inches(5.95), Inches(1.7), Inches(6.8), Inches(5.0), [
            ('What we found', _clip(top['headline'], 170)),
            ('Why it matters', _clip(top['value'], 140)),
            ('Recommended action', _clip(top['fix'], 260)),
        ])

    # Effort and phasing. Phase follows effort unless a finding is pinned to a phase, so the two groupings
    # usually hold the same findings; then one slide says both. When they differ, keep two slides.
    by_tier  = [[f['label'] for f in findings if f['effort_tier'] == t] for t in EFFORT_TIERS]
    by_phase = [[f['label'] for f in findings if f['phase'] == p] for p in (1, 2, 3)]
    if by_tier == by_phase:
        s = _content_slide(prs, 'Effort and phased plan',
                           'Early wins land first; larger work is scheduled behind them.')
        _three_panels(s, [
            (PHASES[p][0], EFFORT_COLOR[EFFORT_TIERS[p - 1]], str(len(by_phase[p - 1])),
             f'{PHASES[p][1]}\n{EFFORT_SUB[EFFORT_TIERS[p - 1]]}', by_phase[p - 1])
            for p in (1, 2, 3)],
            footer=f"{len(by_phase[0])} of {len(findings)} findings take an hour or less and can close in the "
                   'first two weeks')
    else:
        s = _content_slide(prs, 'Deliverables by effort', 'The same findings, grouped by how much work each one takes.')
        _three_panels(s, [
            (tier, EFFORT_COLOR[tier], str(len(lab)), EFFORT_SUB[tier], lab)
            for tier, lab in zip(EFFORT_TIERS, by_tier)],
            footer=f"{len(by_tier[0])} of {len(findings)} findings take an hour or less and can start right away")
        s = _content_slide(prs, 'Phased plan', 'Sequenced so early wins land first and larger work is scheduled.')
        _three_panels(s, [
            (PHASES[p][0].split(' - ')[1], [BLUE, PURPLE, MAGENTA][p - 1], str(len(by_phase[p - 1])),
             f'{PHASES[p][1]}  ·  {PHASES[p][2].lower()} lift', by_phase[p - 1])
            for p in (1, 2, 3)],
            footer=f"{len(by_phase[0])} quick wins can close in the first two weeks; larger work is scheduled behind them")

    # Additional monitoring opportunities: extensions Hub offers for technologies already visible in the tenant's
    # telemetry. Top 10 by volume, grouped by type. Extensions already installed never appear here (the phased plan
    # carries them when they matter).
    ext_opp = tech_discovery.extension_opportunities(data)
    if len(ext_opp) > tech_discovery.SLIDE_MIN_EXCLUSIVE:   # 3 or fewer: too thin for a slide, the report still lists them
        top = ext_opp[:10]
        names = [g[0] for g in tech_discovery.GROUPS]
        groups = []
        for name, color in zip(names, [BLUE, PURPLE, MAGENTA]):
            items = [f"{t['technology']}  ·  {t['volume_label']}" for t in top if tech_discovery.group_of(t['category']) == name]
            total = sum(1 for t in ext_opp if tech_discovery.group_of(t['category']) == name)
            if items:
                groups.append((name, color, str(len(items)), f"{total} available" if len(items) == total else f"top {len(items)} of {total}", items))
        s = _content_slide(prs, 'Additional Monitoring Opportunities',
                           'Technologies already visible in your telemetry that a Dynatrace extension can monitor in more depth.')
        _three_panels(s, groups, max_items=10,
                      footer=f"Top {len(top)} of {len(ext_opp)} extension opportunities, ranked by telemetry volume; the full list is in the report")

    # Optional per-finding slides (off by default - detail lives in the report)
    if detail:
        n = len(findings)
        for i, f in enumerate(findings, 1):
            s = _content_slide(prs, f"Finding {i} of {n}: {f['title']}")
            fix = f['fix'] + (f"\nNo-duplication check: {f['dup_guard']}" if f['dup_guard'] else '')
            finding_panel(s, f, Inches(0.55), Inches(1.7), Inches(12.2), Inches(5.0), [
                ('What we found', f"{f['headline']}\n\n{f['body']}" if f['body'] else f['headline']),
                ('Recommended action', fix),
            ], title='Finding detail', sizes=(13, 12, 11))

    # Close
    close = layout(prs, 'close')
    s = prs.slides.add_slide(close)
    # The corporate "Thank you slide" layout carries its own artwork and title: add nothing to it.
    # report_name and tenant stay in the signature for CLI compatibility but are not shown here.
    if close.name != 'Thank you slide':
        _clear_placeholders(s)
        cover_bg(s)
        add_text(s, 'Thank you', Inches(0.625), Inches(2.9), Inches(8), Inches(1.0),
                 size=34, bold=True, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)

    prs.save(output)
    print(f'Saved: {output}  ({len(active)} findings, {len(prs.slides)} slides)')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Dynatrace Value Roadmap generator')
    ap.add_argument('--customer', required=True, help='Customer display name')
    ap.add_argument('--tenant',   required=True, help='Tenant URL, e.g. abc123.apps.dynatrace.com')
    ap.add_argument('--data',     required=True, nargs='+', help='facts.json then overrides.json (later files win)')
    ap.add_argument('--output',   default=None,  help='Output .pptx path')
    ap.add_argument('--detail',   action='store_true', help='Append one slide per finding')
    ap.add_argument('--report-name', default=None, help='Report filename to reference on the closing slide')
    ap.add_argument('--template', default=None, help='Deck or .potx on the DT 2026 corporate master (overrides the LFS asset)')
    args = ap.parse_args()
    data = load_data(args.data)
    out = args.output or f'{args.customer.replace(" ", "_")}_Value_Roadmap.pptx'
    build(data, args.customer, args.tenant, out, detail=args.detail, report_name=args.report_name, template=args.template)
