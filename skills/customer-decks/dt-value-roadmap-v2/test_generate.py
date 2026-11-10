#!/usr/bin/env python3
"""Self-check for generate_pptx.py scoring/branching logic. Run directly: python3 test_generate.py
No framework, no fixtures - asserts the behavior the opportunity library promises."""
import sys
from generate_pptx import score, plan, fmt, TIER_ORDER, _estate_stats, _exec_overview_bullets, _phase, _hours

BASE = {'hosts': 10, 'services': 5, 'slo_count': 1, 'workflow_count': 1,
        'db_service_pct': 0, 'rum_apps_classic': 0, 'synthetic_monitors': 0,
        'problems_per_day': 0}

# (a) Coverage tier sorts before High Value
data = dict(BASE, oneagent_fullstack_pct=50, slo_count=0)
active = score(data)
keys = [o['key'] for o in active]
assert keys.index('oneagent_coverage') < keys.index('slos'), \
    f'Coverage should sort before High Value, got order {keys}'

# (b) VMware intentionally absent -> no vmware slide at all
data = dict(BASE, vmware_ext_present=False, vmware_ext_intentional=True)
active = score(data)
assert not any(o['key'].startswith('vmware') for o in active), \
    f'Intentional VMware absence should yield zero vmware entries, got {[o["key"] for o in active]}'

# (c) VMware absent and NOT intentional -> gap callout fires (and rides the roadmap via `active`)
data = dict(BASE, vmware_ext_present=False, vmware_ext_intentional=False)
active = score(data)
assert any(o['key'] == 'vmware_data_gap' for o in active), \
    'Unintentional VMware absence should trigger the vmware_data_gap callout'

# (d) Each anomaly in data['anomalies'] renders as one Anomaly-tier entry
data = dict(BASE, anomalies=[
    {'scope': 'cloud', 'entity': 'vm-1', 'metric': 'cpu.usage', 'kind': 'spike',
     'summary': 'CPU spiked 3x baseline', 'recommendation': 'Investigate scaling policy'},
    {'scope': 'vmware', 'entity': 'esxi-2', 'metric': 'datastore.latency', 'kind': 'trend',
     'summary': 'Datastore latency trending up', 'recommendation': 'Check datastore saturation'},
])
active = score(data)
anomaly_entries = [o for o in active if o['priority'] == 'Anomaly']
assert len(anomaly_entries) == 2, f'Expected 2 anomaly entries, got {len(anomaly_entries)}'

assert TIER_ORDER.index('Coverage') < TIER_ORDER.index('Start Here'), 'Coverage must outrank Start Here'

# (e) Estate coverage % folds in cloud/VMware hosts discovered but not yet OneAgent-monitored
est = _estate_stats({'hosts_fullstack': 40, 'hosts_infra': 10,
                      'cloud_hosts_without_oneagent': 5, 'vmware_hosts_without_oneagent': 5})
assert est['total'] == 60, f'Expected 60 total estate hosts, got {est["total"]}'
assert est['coverage_pct'] == 83.3, f'Expected 83.3% coverage, got {est["coverage_pct"]}'
assert _estate_stats({})['coverage_pct'] == 0.0, 'Empty data must not divide by zero'

# (f) Executive overview bullets summarize tier counts and degrade gracefully with no findings
data = dict(BASE, oneagent_fullstack_pct=50, slo_count=0, customer='Acme')
active = score(data)
est = _estate_stats(data)
bullets = _exec_overview_bullets(data, active, est)
assert len(bullets) == 4, f'Expected 4 summary bullets, got {len(bullets)}'
assert 'Top priority' in bullets[-1]
assert _exec_overview_bullets(BASE, [], est)[-1] == 'No material gaps identified in this review.'

# (g) A platform_matrix row for an area supersedes the generic library slide (no duplicate slides)
row = {'area': 'Problem notifications', 'status': 'Gen2', 'gen2': 'classic notifications',
       'gen3': 'workflows', 'next_step': 'Build workflows', 'duplication_check': 'Disable classic channel'}
data = dict(BASE, workflow_count=0, platform_matrix=[row])
keys = [o['key'] for o in score(data)]
assert 'workflows' not in keys and 'upgrade_Problem notifications' in keys, keys

# (h) Gen3-only rows never produce an upgrade slide; Both/duplicate rows are 'consolidate', not 'add'
data = dict(BASE, platform_matrix=[
    {'area': 'AWS monitoring', 'status': 'Gen3', 'gen2': '-', 'gen3': 'AWS connection'},
    {'area': 'Metric events', 'status': 'Both', 'duplicate': True, 'gen2': 'metric events', 'gen3': 'anomaly detectors'}])
up = [o for o in score(data) if o['priority'] == 'Upgrade']
assert [o['key'] for o in up] == ['upgrade_Metric events'], [o['key'] for o in up]
assert up[0]['gen'] == 'Both' and up[0]['label'].startswith('Consolidate'), up[0]

# (i) When most logs arrive via a forwarder, the log fix is 'pick one path', never 'enable OneAgent logs'
data = dict(BASE, customer='Acme', pg_with_logs_pct=0, process_groups=10, log_external_pct=83,
            log_external_source='AWS Firehose', log_records_24h=100, log_unattributed_pct=100)
f = {x['key']: x for x in plan(data)}
assert 'one log path' in f['log_enablement']['fix'].lower(), f['log_enablement']['fix']
assert f['log_enablement']['dup_guard'], 'external-log branch must carry a duplication check'
assert 'Enable log monitoring' not in f['log_enablement']['action'], f['log_enablement']['action']
assert 'log_to_trace' not in f, 'log_to_trace is suppressed when no OneAgent logs exist'

# (j) DB extensions already reporting -> no database_extensions recommendation
data = dict(BASE, db_service_pct=60, db_extensions_present=['MySQL'])
assert 'database_extensions' not in [o['key'] for o in score(data)]

# (k) Phasing by lift: <=1h phase 1, <=1 day phase 2, longer phase 3
assert _hours('15 min') == 0.25 and _hours('1-2 days') == 16 and _hours('1 week') == 40
assert _phase({'effort': '30 min'}) == 1 and _phase({'effort': '3 hr'}) == 2
assert _phase({'effort': '2-3 days'}) == 3 and _phase({'effort': '15 min', 'phase': 3}) == 3

# (l) SE pins and overrides: pinned keys lead; label/effort overrides apply
data = dict(BASE, slo_count=0, oneagent_fullstack_pct=50, hosts_fullstack=5, hosts_total=10, hosts_infra=5,
            top_priorities=['slos'], label_overrides={'slos': 'Define SLOs'}, effort_overrides={'slos': '1 week'})
first = plan(dict(data, customer='Acme'))[0]
assert first['key'] == 'slos' and first['label'] == 'Define SLOs' and first['phase'] == 3, first

# (m) Every active finding renders all text fields without leaving format braces behind
data = dict(BASE, customer='Acme', slo_count=0, workflow_count=0, notifications_count=3,
            problems_per_day=500, problems_per_week=3500, top_problem_sources=[['ECS CPU', 900]],
            alerting_profiles=4, alerting_profiles_no_rules=['VPN'], mz_issues=['x'], mz_count=2,
            hosts_ip_named=9, hosts_total=10, generic_services=['/'], hosts_cpu_ge60=2,
            log_retention_days=35, traces_per_day='1M')
for x in plan(data):
    for k in ('title', 'headline', 'body', 'fix', 'action', 'value', 'label'):
        assert '{' not in x[k], f"{x['key']}.{k} left an unformatted placeholder: {x[k]!r}"

# (n) custom_findings render in their tier with effort/phase carried through
data = dict(BASE, customer='Acme', custom_findings=[{'key': 'vpc_flow_volume', 'tier': 'Config Fix', 'title': 'VPC flow logs drive ingest',
            'label': 'Filter VPC flow logs', 'next_step': 'Drop accepted-traffic records', 'effort': '1 day', 'phase': 2}])
f = {x['key']: x for x in plan(data)}
assert f['vpc_flow_volume']['tier'] == 'Config Fix' and f['vpc_flow_volume']['phase'] == 2, f['vpc_flow_volume']

# (o) Customer-facing text never uses the word "cost" (or DPS/price/billing): findings carry effort and
# value only, even when an older overrides.json still supplies cost / line_item keys.
import re
BANNED = re.compile(r'cost|dps|pric(e|ing)|billing', re.I)
data = dict(BASE, customer='Acme', slo_count=0, workflow_count=0, notifications_count=3, oneagent_fullstack_pct=50,
            hosts_fullstack=5, hosts_total=10, hosts_infra=5, problems_per_day=500, problems_per_week=3500,
            alerting_profiles=4, alerting_profiles_no_rules=['VPN'], mz_issues=['x'], mz_count=2, hosts_ip_named=9,
            generic_services=['/'], hosts_cpu_ge60=2, log_retention_days=35, traces_per_day='1M',
            db_service_pct=60, db_services=6, highlight_tagging=True, cloud_providers_in_use='AWS',
            custom_findings=[{'key': 'legacy', 'tier': 'Config Fix', 'title': 'Legacy', 'cost': 'Higher Cost',
                              'line_item': 'Something', 'effort': '2 hr'}])
for x in plan(data):
    assert 'cost' not in x and 'cost_tier' not in x and 'line_item' not in x, x['key']
    for k in ('title', 'headline', 'body', 'fix', 'action', 'value', 'label', 'dup_guard'):
        assert not BANNED.search(x[k]), f"{x['key']}.{k} mentions cost/billing: {x[k]!r}"

# (p) The written report and a full deck build render without cost wording and with the effort sections
import tempfile, os
from generate_report import content, to_markdown
md = to_markdown(content(data, 'Acme', 'x.apps.dynatrace.com', 'SE', 'today'))
assert not BANNED.search(md), BANNED.search(md).group(0)
assert 'Effort and Value Breakdown' in md and 'Low Effort' in md
from generate_pptx import build
from pptx import Presentation
with tempfile.TemporaryDirectory() as d:
    out = os.path.join(d, 'deck.pptx')
    build(dict(data, platform_matrix=[{'area': 'SLOs', 'status': 'Gen3'}]), 'Acme', 'x.apps.dynatrace.com', out, detail=True)
    text = ' '.join(sh.text_frame.text for sl in Presentation(out).slides for sh in sl.shapes if sh.has_text_frame)
    assert not BANNED.search(text), BANNED.search(text).group(0)
    assert 'Where to start' in text and 'Observability Gap Analysis' in text

# (q) Effort and phase slides merge when they hold the same findings, and stay separate when they differ
def _titles(d):
    with tempfile.TemporaryDirectory() as t:
        out = os.path.join(t, 'd.pptx'); build(dict(d), 'Acme', 'x', out)
        return [sh.text_frame.text for sl in Presentation(out).slides for sh in sl.shapes
                if sh.has_text_frame and sh.text_frame.text in ('Effort and phased plan', 'Deliverables by effort', 'Phased plan')]
same = dict(BASE, slo_count=0, workflow_count=1)
assert _titles(same) == ['Effort and phased plan'], _titles(same)
split = dict(same, anomalies=[{'scope': 'service', 'entity': 'svc', 'metric': 'failure rate', 'kind': 'trend',
             'severity': 'high', 'summary': 's', 'recommendation': 'r', 'effort': '3 hr'}])
assert _titles(split) == ['Deliverables by effort', 'Phased plan'], _titles(split)


# (k) Extension opportunities: installed/flowing/no-Hub entries never surface; ranked by volume; top 10 on the slide
import tech_discovery as td
def _t(name, cat, status, vol=0, inst=0, hub=True, logs=0):
    return dict(technology=name, category=cat, status=status, calls=vol, log_records=logs, instances=inst, volume_label=td.volume_label(vol, logs, inst),
                hub_candidates=[{'id': 'x', 'name': name}] if hub else [], evidence=['e'])
OPP = 'Opportunity: extension available in Hub'
d = {'tech_opportunities': [
    _t('Small DB', 'Database', OPP, vol=10), _t('Big DB', 'Database', OPP, vol=5_000_000),
    _t('Installed DB', 'Database', 'Extension installed and configured', vol=9_000_000_000),
    _t('Flowing', 'Database', 'Extension data already flowing', vol=9_000_000_000),
    _t('Unconfigured', 'Messaging', 'Extension installed, no monitoring configuration', vol=9_000_000_000),
    _t('No hub', 'Web / proxy', 'Detected, no matching Hub extension found', vol=9_000_000_000, hub=False),
    _t('Proc only', 'Web / proxy', OPP, inst=40)]}
names = [t['technology'] for t in td.extension_opportunities(d)]
assert names == ['Big DB', 'Small DB', 'Proc only'], f'Unexpected opportunity list/order: {names}'
assert td.group_of('Database') == 'Databases and data' and td.group_of('Messaging') == 'Messaging and integration'
assert td.group_of('Network / security') == 'Infrastructure and security'
assert td.volume_label(83_500_000, 0, 0) == '83.5M calls/hr' and td.volume_label(0, 0, 19) == '19 process instances'
assert td.volume_label(0, 20_700_000, 5) == '20.7M log records/hr' and td.volume_label(0, 0, 1) == '1 process instance'
# trace-call technologies outrank a log-only technology even when the log count is far larger
d2 = {'tech_opportunities': [_t('Chatty logs', 'Platform tooling', OPP, logs=20_000_000), _t('Calls', 'Database', OPP, vol=1000), _t('Procs', 'Web / proxy', OPP, inst=500)]}
assert [t['technology'] for t in td.extension_opportunities(d2)] == ['Calls', 'Chatty logs', 'Procs']

# (l) Slide threshold: 3 or fewer opportunities -> no slide; 4 -> slide
from pptx import Presentation
import generate_pptx as gp, tempfile, os as _os
def _slides(n):
    dd = dict(BASE, tech_opportunities=[_t(f'T{i}', 'Database', OPP, vol=100 - i) for i in range(n)])
    out = _os.path.join(tempfile.mkdtemp(), 'x.pptx'); gp.build(dd, 'Acme', 'x.apps.dynatrace.com', out)
    return [sh.text_frame.text for sl in Presentation(out).slides for sh in sl.shapes if sh.has_text_frame]
assert 'Additional Monitoring Opportunities' not in _slides(3), 'Slide must be skipped for 3 or fewer opportunities'
assert 'Additional Monitoring Opportunities' in _slides(4), 'Slide must appear for 4 opportunities'

print('All checks passed.')
