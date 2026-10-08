#!/usr/bin/env python3
"""Self-check for generate_pptx.py scoring/branching logic. Run directly: python3 test_generate.py
No framework, no fixtures - asserts the behavior the opportunity library promises."""
import sys
from generate_pptx import score, TIER_ORDER, _estate_stats, _exec_overview_bullets

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

print('All checks passed.')
