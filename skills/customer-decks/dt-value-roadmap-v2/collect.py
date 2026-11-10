#!/usr/bin/env python3
"""
dt-value-roadmap-v2: deterministic data collection.

Runs every known-good query and settings pull SEQUENTIALLY (parallel dtctl calls have wiped OAuth
tokens), derives the data.json fields the generators need, and writes:

  <out>/facts.json    - data.json-compatible fields + an "_evidence" block for the model to judge
  <out>/digest.md     - a short summary of what is unusual (the only file the model needs to read)
  <out>/raw/          - every raw query/settings result, for debugging

Usage:
  python collect.py --context "<dtctl context>" --out <dir> [--readiness] [--prod-prefixes p]
"""
import argparse, json, os, re, subprocess, sys, tempfile, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tech_discovery

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_ROOT = os.path.dirname(os.path.dirname(SKILL_DIR))  # .../skills/
# ponytail: names the migration/ category directly (dt-upgrade-readiness isn't a sibling
# of this skill post-reorg) — update if dt-upgrade-readiness changes category or name
READINESS = os.path.join(SKILLS_ROOT, 'migration', 'dt-upgrade-readiness', 'scripts', 'collect.py')

class Collector:
    def __init__(self, ctx, out):
        self.ctx, self.out = ctx, out
        self.raw = os.path.join(out, 'raw'); os.makedirs(self.raw, exist_ok=True)
        self.errors, self.warnings = [], []

    def _run(self, args, name):
        p = subprocess.run(['dtctl', *args, '--context', self.ctx], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=600)
        if 'scan' in p.stderr.lower() and 'limit' in p.stderr.lower():
            self.warnings.append(f'{name}: hit the Grail scan limit - result is partial')
        return p

    def q(self, name, dql):
        """DQL via a file (PowerShell strips inline quotes). Returns list of records, [] on error."""
        with tempfile.NamedTemporaryFile('w', suffix='.dql', delete=False, encoding='utf-8') as f:
            f.write(dql); path = f.name
        try:
            p = self._run(['query', '-f', path, '-o', 'json'], name)
        finally:
            os.unlink(path)
        if p.returncode != 0:
            self.errors.append(f'{name}: {p.stderr.strip()[:160]}'); return []
        try:
            j = json.loads(p.stdout)
        except ValueError:
            self.errors.append(f'{name}: unparseable output'); return []
        recs = j.get('records', j) if isinstance(j, dict) else j
        json.dump(recs, open(os.path.join(self.raw, f'{name}.json'), 'w', encoding='utf-8'))
        return recs or []

    def one(self, name, dql):
        r = self.q(name, dql)
        return r[0] if r else {}

    def get(self, name, *args):
        """dtctl get ... -o json. Returns list, or None on error (403 recorded)."""
        p = self._run(['get', *args, '--no-agent', '-o', 'json'], name)
        if p.returncode != 0:
            self.errors.append(f'{name}: {p.stderr.strip()[:160]}'); return None
        try:
            j = json.loads(p.stdout)
        except ValueError:
            self.errors.append(f'{name}: unparseable output'); return None
        json.dump(j, open(os.path.join(self.raw, f'{name}.json'), 'w', encoding='utf-8'))
        return j if isinstance(j, list) else [j]

    def settings(self, schema):
        return self.get(schema.replace('builtin:', ''), 'settings', f'--schema={schema}')

def num(x, d=0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d

def short(name):
    return str(name or '').split('.')[0].lower()

def human(n):
    n = num(n)
    for div, s in ((1e9, 'B'), (1e6, 'M'), (1e3, 'K')):
        if n >= div:
            v = n / div
            return f"{v:.1f}{s}".replace('.0' + s, s) if v < 10 else f"{v:.0f}{s}"
    return str(int(n))

# ── COLLECTION ───────────────────────────────────────────────────────────────
def collect(c, a):
    F, E = {}, {}   # facts (data.json fields), evidence (for model judgment)

    # Hosts: live smartscape HOST joined to ONEAGENT (fetch dt.entity.host includes retired entities)
    hosts = c.q('hosts_live', '''smartscapeNodes "HOST"
| fieldsAdd hid = toString(id)
| lookup [smartscapeNodes "ONEAGENT" | fieldsAdd host_ref = toString(references[monitors.host][0]), mode = dt.agent.monitoring_mode], sourceField:hid, lookupField:host_ref
| fields name, mode = lookup.mode, aws_id = aws.resource.id''')
    F['hosts_fullstack'] = sum(1 for h in hosts if h.get('mode') == 'FULL_STACK')
    F['hosts_infra'] = sum(1 for h in hosts if h.get('mode') == 'INFRASTRUCTURE')
    F['hosts'] = F['hosts_total'] = F['hosts_fullstack'] + F['hosts_infra']
    F['oneagent_fullstack_pct'] = round(100 * F['hosts_fullstack'] / F['hosts_total']) if F['hosts_total'] else 0
    F['hosts_ip_named'] = sum(1 for h in hosts if str(h.get('name', '')).startswith('ip-'))
    host_short = {short(h.get('name')) for h in hosts}
    host_aws = {h.get('aws_id') for h in hosts if h.get('aws_id')}
    E['hosts_without_mode'] = sum(1 for h in hosts if not h.get('mode'))

    grp = c.q('host_groups', 'fetch dt.entity.host, from:now()-24h | filter isNotNull(monitoringMode) | summarize n=count(), by:{hostGroupName}')
    F['host_groups'] = sum(1 for g in grp if g.get('hostGroupName'))
    infra = c.q('infra_hosts', 'fetch dt.entity.host, from:now()-24h | filter monitoringMode == "INFRASTRUCTURE" | summarize n=count(), by:{hostGroupName}')
    E['infra_by_host_group'] = {str(i.get('hostGroupName') or '(none)'): int(num(i['n'])) for i in infra}
    tg = c.one('host_tags', 'fetch dt.entity.host, from:now()-24h | filter isNotNull(monitoringMode) | fieldsAdd n=arraySize(tags) | summarize hosts=count(), tagged=countIf(n>0)')
    E['hosts_tagged'] = f"{tg.get('tagged')} of {tg.get('hosts')} seen in 24h"

    # Services and request volume
    F['services'] = int(num(c.one('services', 'fetch dt.entity.service, from:now()-24h | summarize n=count()').get('n')))
    F['db_services'] = int(num(c.one('db_services', 'fetch dt.entity.service, from:now()-24h | filter serviceType == "DATABASE_SERVICE" | summarize n=count()').get('n')))
    F['db_service_pct'] = round(100 * F['db_services'] / F['services']) if F['services'] else 0
    F['process_groups'] = int(num(c.one('pgs', 'fetch dt.entity.process_group, from:now()-24h | summarize n=count()').get('n')))
    st = c.one('svc_tags', 'fetch dt.entity.service, from:now()-24h | fieldsAdd n=arraySize(tags) | summarize s=count(), t=countIf(n>0)')
    E['services_tagged'] = f"{st.get('t')} of {st.get('s')}"
    F['traces_per_day'] = human(c.one('requests', 'timeseries v=sum(dt.service.request.count), from:now()-24h | fields t=arraySum(v)').get('t'))
    gen = c.q('generic_services', 'fetch dt.entity.service, from:now()-24h | filter entity.name == "/" or startsWith(entity.name, "localhost") or contains(entity.name, "Tomcat/localhost") or startsWith(entity.name, "Requests on 127.0.0.1") or entity.name == "Default Web Site" | fields entity.name')
    names = sorted({g['entity.name'] for g in gen})
    lh = [n for n in names if n.startswith('localhost')]
    F['generic_services'] = ([f'localhost ({len(lh)} services)'] if len(lh) > 1 else lh) + [n for n in names if not n.startswith('localhost')]
    top = c.q('top_services', 'timeseries t=sum(dt.service.request.count), by:{dt.entity.service}, from:now()-7d | fieldsAdd vol=arraySum(t), name=entityName(dt.entity.service) | sort vol desc | limit 10 | fields name, vol')
    E['top_services_7d'] = [(t['name'], human(t['vol'])) for t in top]
    um = [t for t in top if t['name'] == 'Requests to unmonitored hosts']
    if um:
        F['unmonitored_requests_week'] = human(um[0]['vol'])

    # Problems: weekly and daily, top sources, 3-hour bursts
    F['problems_per_week'] = int(num(c.one('problems_7d', 'fetch dt.davis.problems, from:now()-7d | summarize n=countDistinctExact(display_id)').get('n')))
    F['problems_per_day'] = round(F['problems_per_week'] / 7)
    E['problems_last_24h'] = int(num(c.one('problems_24h', 'fetch dt.davis.problems, from:now()-24h | summarize n=countDistinctExact(display_id)').get('n')))
    ts = c.q('top_problems', 'fetch dt.davis.problems, from:now()-7d | dedup display_id | summarize n=count(), by:{event.name} | sort n desc | limit 6')
    F['top_problem_sources'] = [[t['event.name'], int(num(t['n']))] for t in ts]
    b = c.one('problem_buckets', 'fetch dt.davis.problems, from:now()-7d | dedup display_id | makeTimeseries n=count(), interval:3h')
    buckets = [num(x) for x in (b.get('n') or []) if x is not None]
    if buckets:
        mx, avg = max(buckets), sum(buckets) / len(buckets)
        start = (b.get('timeframe') or {}).get('start', '')
        if mx >= 30 and mx >= 4 * avg:
            i = buckets.index(mx)
            E['problem_burst'] = f"{int(mx)} problems in one 3h window (bucket {i} from {start[:16]}), average {avg:.0f} per 3h"

    # CPU: two weeks, ephemeral batch workers excluded
    eph = re.compile(a.ephemeral, re.I)
    def cpu(name, frm, to=''):
        r = c.q(name, f'timeseries c=avg(dt.host.cpu.usage), by:{{dt.entity.host}}, from:{frm}{", to:" + to if to else ""} | fieldsAdd a=arrayAvg(c), p95=arrayPercentile(c, 95), name=entityName(dt.entity.host) | filter a >= 55 | fields name, a, p95')
        return {x['name']: x for x in r if not eph.search(str(x['name']))}
    now, prior = cpu('cpu_7d', 'now()-7d'), cpu('cpu_prior', 'now()-14d', 'now()-7d')
    hot = [(n, round(num(x['a']), 1), round(num(x['p95']), 1)) for n, x in now.items() if num(x['a']) >= 60]
    F['hosts_cpu_ge60'] = len(hot)
    if hot:
        F['cpu_max_avg'] = max(h[1] for h in hot); F['cpu_max_p95'] = max(h[2] for h in hot)
    E['cpu_hot_persistent'] = [h for h in sorted(hot, key=lambda h: -h[1]) if h[0] in prior][:8]

    # Service failure rate week over week -> anomaly candidates
    def fr(name, frm, to=''):
        r = c.q(name, f'timeseries {{f=sum(dt.service.request.failure_count), t=sum(dt.service.request.count)}}, by:{{dt.entity.service}}, from:{frm}{", to:" + to if to else ""} | fieldsAdd fr=100*arraySum(f)/arraySum(t), vol=arraySum(t) | filter vol > 10000 and fr > 15 | fieldsAdd name=entityName(dt.entity.service) | fields id=dt.entity.service, name, fr, vol | sort fr desc | limit 40')
        return {x['id']: x for x in r}
    fn, fp = fr('failrate_7d', 'now()-7d'), fr('failrate_prior', 'now()-14d', 'now()-7d')
    rising, chronic = [], []
    for sid, x in fn.items():
        n, p = num(x['fr']), num(fp.get(sid, {}).get('fr'), None)
        if p is not None and n >= 80 and p >= 80:
            chronic.append((x['name'], round(n), human(x['vol'])))
        elif (p is None or n - p >= 8) and n >= 20:
            rising.append((x['name'], None if p is None else round(p), round(n), human(x['vol'])))
    dedup = lambda xs: list({x[0]: x for x in xs}.values())
    E['failrate_rising'], E['failrate_chronic'] = dedup(rising)[:8], dedup(chronic)[:8]

    # Logs: 1-hour window only (24h scans hit the 500 GB scan cap)
    src = c.q('log_sources_1h', 'fetch logs, from:now()-1h | summarize n=count(), no_host=countIf(isNull(dt.entity.host)), no_svc=countIf(isNull(dt.entity.service)), tr=countIf(isNotNull(trace_id)), by:{dt.openpipeline.source, dt.system.bucket} | sort n desc | limit 15')
    tot = sum(num(s['n']) for s in src)
    F['log_records_24h'] = int(tot * 24)
    oa = [s for s in src if s.get('dt.openpipeline.source') == 'oneagent']
    oa_n = sum(num(s['n']) for s in oa)
    fwd = [s for s in src if re.search(r'firehose|eventhub|event_hub|pubsub', str(s.get('dt.openpipeline.source')), re.I)]
    fwd_n = sum(num(s['n']) for s in fwd)
    if tot:
        F['log_unattributed_pct'] = round(100 * sum(num(s['no_host']) for s in src) / tot)
        F['log_external_pct'] = round(100 * fwd_n / tot)
        F['log_to_trace_pct'] = round(100 * sum(num(s['tr']) for s in oa) / oa_n) if oa_n else 0
        if fwd:
            F['log_external_source'] = 'AWS Firehose' if 'firehose' in str(fwd[0]['dt.openpipeline.source']).lower() else str(fwd[0]['dt.openpipeline.source'])
    F['log_sources'] = [f"{s['dt.openpipeline.source']} ({human(num(s['n']) * 24)}/day)" for s in src[:5]]
    pgl = c.one('log_pgs_1h', 'fetch logs, from:now()-1h | filter isNotNull(dt.entity.process_group) | summarize n=countDistinctExact(dt.entity.process_group)')
    F['pg_with_logs_pct'] = round(100 * num(pgl.get('n')) / F['process_groups']) if F['process_groups'] else 0
    if fwd:
        lg = c.q('forwarder_groups_1h', 'fetch logs, from:now()-1h | filter isNotNull(aws.log_group) | summarize n=count(), by:{aws.log_group} | sort n desc | limit 6')
        E['forwarder_top_log_groups_per_hour'] = [(g['aws.log_group'], human(g['n'])) for g in lg]

    # Cloud: metric namespaces, Gen3 connections, uncovered instances
    ns = c.q('cloud_metrics', 'fetch metric.series, from:now()-24h | filter startsWith(metric.key, "cloud.") | fieldsAdd p=splitString(metric.key, ".") | fieldsAdd ns=concat(p[0], ".", p[1]) | summarize keys=countDistinctExact(metric.key), by:{ns, dt.source}')
    E['cloud_metric_namespaces'] = [(n['ns'], n.get('dt.source'), int(num(n['keys']))) for n in ns]
    for p in ('aws', 'azure', 'gcp'):
        conns = c.settings(f'builtin:hyperscaler-authentication.connections.{p}')
        E[f'gen3_{p}_connections'] = len(conns) if conns is not None else 'error'
    providers = sorted({n['ns'].split('.')[1] for n in ns})
    F['cloud_providers_in_use'] = ' and '.join(p.upper() if p in ('aws', 'gcp') else p.capitalize() for p in providers)
    F['cloud_integration_live'] = bool(providers)
    ec2 = c.q('ec2_running', 'smartscapeNodes "AWS_EC2_INSTANCE" | filter aws.state == "running" | fields name, aws.resource.id')
    az = c.q('azure_vms', 'smartscapeNodes "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES" | fields name, azure.resource.group')
    vdi = re.compile(a.vdi, re.I)
    az_srv = [v for v in az if not vdi.search(str(v.get('name'))) and not vdi.search(str(v.get('azure.resource.group')))]
    gaps = [e['name'] for e in ec2 if e.get('aws.resource.id') not in host_aws] + \
           [v['name'] for v in az_srv if short(v['name']) not in host_short]
    F['cloud_hosts_running'] = len(ec2) + len(az_srv)
    F['cloud_hosts_without_oneagent'] = len(gaps)
    cnt = {}
    for g in gaps:
        cnt[g or 'unnamed instance'] = cnt.get(g or 'unnamed instance', 0) + 1
    F['cloud_hosts_without_oneagent_names'] = [f'{k} (x{v})' if v > 1 else k for k, v in cnt.items()][:10]
    E['azure_vms'] = f"{len(az)} total, {len(az) - len(az_srv)} VDI, {len(az_srv)} servers"
    F['cloud_k8s_clusters'] = int(num(c.one('k8s', 'fetch dt.entity.kubernetes_cluster, from:now()-24h | summarize n=count()').get('n')))

    # VMware: Gen3 integration, VMs split prod vs non-prod by naming convention
    vk = int(num(c.one('vmware_keys', 'fetch metric.series, from:-7d | filter contains(metric.key, "vmware") | summarize n=countDistinctExact(metric.key)').get('n')))
    F['vmware_ext_present'] = vk > 0
    if vk:
        F['vmware_hosts'] = int(num(c.one('vmware_hypervisors', 'timeseries v=avg(dt.cloud.vmware.hypervisor.cpu.usage), by:{dt.entity.hypervisor}, from:-7d | summarize n=count()').get('n')))
        vms = c.q('vmware_vms', 'timeseries v=avg(dt.cloud.vmware.vm.cpu.usage), by:{dt.entity.virtualmachine}, from:-24h | fieldsAdd name=entityName(dt.entity.virtualmachine) | fields name')
        F['vmware_vms'] = len(vms)
        prod = [v for v in vms if any(str(v['name']).lower().startswith(p) for p in a.prod_prefixes.split(','))]
        prod_gap = [v['name'] for v in prod if short(v['name']) not in host_short]
        F['vmware_hosts_without_oneagent'] = len(prod_gap)
        by_prefix = {}
        for n in prod_gap:
            by_prefix[str(n)[:2].lower()] = by_prefix.get(str(n)[:2].lower(), 0) + 1
        E['vmware_prod_vms'] = f"{len(prod)} production-named, {len(prod) - len(prod_gap)} with OneAgent, {len(vms) - len(prod)} non-prod excluded"
        E['vmware_prod_gap_by_prefix'] = by_prefix

    # Synthetics, RUM, DB extensions
    F['synthetic_monitors'] = sum(int(num(c.one(f'synth_{t}', f'fetch dt.entity.{t}, from:now()-24h | summarize n=count()').get('n')))
                                  for t in ('http_check', 'synthetic_test', 'multiprotocol_monitor'))
    F['grail_rum_active'] = num(c.one('user_events', 'fetch user.events, from:now()-24h | limit 1 | summarize n=count()').get('n')) > 0
    dbx = c.q('db_ext_metrics', 'fetch metric.series, from:-24h | filter startsWith(metric.key, "sql-") or startsWith(metric.key, "oracle") or startsWith(metric.key, "postgres") or startsWith(metric.key, "mysql") or startsWith(metric.key, "mongodb") | fieldsAdd p=splitString(metric.key, ".")[0] | summarize n=countDistinctExact(metric.key), by:{p}')
    F['db_extensions_present'] = [d['p'] for d in dbx]

    # Technologies the tenant already emits telemetry for, mapped to Hub extensions (installed / configured / available)
    tech_discovery.discover(c, F, E)

    # Settings and Gen3 resources
    ap = c.settings('builtin:alerting.profile') or []
    nt = c.settings('builtin:problem.notifications') or []
    mz = c.settings('builtin:management-zones') or []
    me = c.settings('builtin:anomaly-detection.metric-events') or []
    ad = c.settings('builtin:davis.anomaly-detectors') or []
    slo = c.settings('builtin:monitoring.slo') or []
    rum = c.settings('builtin:rum.web.app-detection') or []
    wf = c.get('workflows', 'workflows')
    seg = c.get('segments', 'segments') or []
    bk = c.get('buckets', 'buckets') or []
    gslo = c.get('slos', 'slos')

    F['alerting_profiles'], F['notifications_count'] = len(ap), len(nt)
    F['notifications_enabled'] = sum(1 for n in nt if n['value'].get('enabled'))
    F['workflow_count'] = len(wf) if wf is not None else 0
    def notif_label(p):
        ns_ = [n['value'] for n in nt if n['value'].get('alertingProfile') == p['objectId']]
        live = [n for n in ns_ if n.get('enabled')]
        return (f"live {live[0].get('type', '').lower()} attached" if live else
                'notification attached but disabled' if ns_ else 'no notification attached'), bool(live), bool(ns_)
    no_rules, test, orphan = [], [], []
    for p in ap:
        v = p['value']; lbl, live, anyn = notif_label(p)
        if not v.get('severityRules'):
            no_rules.append(f"{v['name']} ({lbl})")
        if re.search(r'\btest\b', v['name'], re.I) and live:
            test.append(f"{v['name']} ({lbl})")
        if not anyn and not v['name'].startswith('Default'):
            orphan.append(v['name'])
    F['alerting_profiles_no_rules'], F['alerting_profiles_test'] = no_rules, test
    if F['workflow_count'] == 0:
        F['alerting_profiles_orphaned'] = orphan      # with workflows present they may be workflow triggers
    E['profiles_without_notification'] = orphan

    mzh = c.q('mz_hosts', 'fetch dt.entity.host, from:now()-24h | filter isNotNull(monitoringMode) | expand mz=managementZones | summarize n=count(), by:{mz}')
    mzs = c.q('mz_services', 'fetch dt.entity.service, from:now()-24h | expand mz=managementZones | summarize n=count(), by:{mz}')
    mza = c.q('mz_apps', 'fetch dt.entity.application, from:now()-24h | expand mz=managementZones | summarize n=count(), by:{mz}')
    members = {m.get('mz') for m in mzh + mzs + mza if m.get('mz')}
    issues = []
    empty = [z['value']['name'] for z in mz if z['value']['name'] not in members]
    if empty:
        more = f" and {len(empty) - 6} more" if len(empty) > 6 else ''
        issues.append(f"{len(empty)} {'zone matches' if len(empty) == 1 else 'zones match'} no hosts, services, "
                      f"or applications today: {', '.join(empty[:6])}{more}.")
    for z in mz:
        ids = re.findall(r'"entityId":\s*"([A-Z_]+-[0-9A-F]+)"', json.dumps(z['value']))
        if ids:
            issues.append(f"{z['value']['name']} pins a rule to {ids[0]}; it stops matching when that entity is replaced.")
    nomz = sum(int(num(m['n'])) for m in mzs if not m.get('mz'))
    if mz and nomz and F['services'] and nomz / F['services'] > 0.3:
        issues.append(f"{nomz:,} of {F['services']:,} services sit in no management zone.")
    F['mz_count'], F['mz_issues'] = len(mz), issues
    F['custom_segment_count'] = sum(1 for s in seg if s.get('owner') != 'Dynatrace')

    me_on = [m['value'] for m in me if m['value'].get('enabled')]
    def sel(m):
        q_ = m.get('queryDefinition') or {}
        return q_.get('metricSelector') or q_.get('metricKey') or ''
    E['metric_events'] = f"{len(me)} classic ({len(me_on)} enabled); selectors: " + ', '.join(sorted({re.split(r'[:.(]', sel(m))[0] for m in me_on})[:6])
    # Classic builtin:cloud / ext:cloud metrics live in classic metric storage, not Grail metric.series,
    # so their data can't be checked with DQL. Use Davis events instead: an event raised in the last
    # 30 days proves the metric reports. No event means quiet OR no data - never call it dead.
    # (title, summary) pairs: several events can share one event title (e.g. a copy scoped to another team).
    classic_cloud = [((m.get('eventTemplate') or {}).get('title') or m.get('summary', ''), m.get('summary', ''))
                     for m in me_on if re.match(r'(ext:cloud|builtin:cloud)', sel(m))]
    if classic_cloud:
        titles = ', '.join(json.dumps(t) for t in sorted({t for t, _ in classic_cloud}))
        fired = {r.get('event.name') for r in c.q('metric_event_activity_30d',
                 f'fetch dt.davis.events, from:now()-30d | filter in(event.name, array({titles})) '
                 '| summarize n=count(), by:{event.name}')}
        E['metric_events_cloud_fired'] = [s for t, s in classic_cloud if t in fired]
        E['metric_events_cloud_quiet'] = [s for t, s in classic_cloud if t not in fired]
    E['anomaly_detectors'] = f"{len(ad)} Gen3 ({sum(1 for x in ad if x['value'].get('enabled'))} enabled, {sum(1 for x in ad if re.search('test', x['value'].get('title', ''), re.I))} named test)"
    F['classic_slo_count'] = len(slo)
    E['classic_slo_templated'] = sum(1 for s in slo if re.match(r'(Availability|Performance) SLO', s['value'].get('name', '')))
    F['slo_count'] = len(gslo) if gslo is not None else None
    F['rum_apps_classic'] = len(rum)
    if wf:
        titles = [w.get('title') for w in wf]
        E['workflows_duplicated'] = sorted({t for t in titles if titles.count(t) > 1})
    logb = [b_ for b_ in bk if b_.get('table') == 'logs']
    F['log_retention_days'] = next((int(b_['retentionDays']) for b_ in logb if b_.get('bucketName') == 'default_logs'), 35)
    E['log_buckets'] = [(b_['bucketName'], b_['retentionDays']) for b_ in logb]
    return F, E

# ── READINESS DIGEST ─────────────────────────────────────────────────────────
def readiness(c, ctx):
    path = os.path.join(c.raw, 'readiness.json')
    env = dict(os.environ, PYTHONUTF8='1')
    with open(path, 'w', encoding='utf-8') as fh:
        p = subprocess.run([sys.executable, '-X', 'utf8', READINESS, '--context', ctx, '--workers', '1'],
                           stdout=fh, stderr=subprocess.PIPE, text=True, env=env, timeout=1800)
    if p.returncode != 0:
        c.errors.append(f'readiness: {p.stderr.strip()[-200:]}'); return None
    return digest_readiness(json.load(open(path, encoding='utf-8')))

def _cell(v):
    s = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', str(v))      # drop markdown link targets
    return s[:60]

# Column that names a row, in preference order; the first string column is the fallback.
_NAME_KEYS = ('Service', 'Frontend', 'Host', 'Cluster', 'Alert name', 'Credential', 'Queue', 'Setting', 'Scope',
              'metric.key', 'Request attribute', 'Name', 'Guardian', 'Data type', 'Status', 'Pipeline')
_SKIP_KEYS = ('Action', 'id', 'By', 'Last Updated', 'Last changed', 'Modified', 'interval', 'timeframe', 'Usage trend')

def _fields(row):
    return {k: v for k, v in row.items() if k not in _SKIP_KEYS and not isinstance(v, (list, dict))}

def _zeroish(v):
    s = _cell(v).strip()
    return s in ('', '0', '0.0', 'None', 'null') or s.startswith('🟢')

def digest_readiness(j):
    """One line per check that needs attention. Dropped: green, empty, all-zero, and trend-chart checks."""
    lines = [f"Scope gaps: {', '.join(j.get('scope_gaps') or []) or 'none'}"]
    for s in j['sections']:
        out = []
        for ch in s['checks']:
            title = ch.get('title') or ch['id']
            if ch.get('error'):
                out.append(f"- {title}: could not run"); continue
            r, st = ch.get('result'), ch.get('status', '')
            if ch.get('skipped') or st.startswith('🟢') or 'over time' in title or r in ([], None, 0, '0'):
                continue
            if isinstance(r, list) and r and isinstance(r[0], dict):
                rows = [f for f in (_fields(x) for x in r) if f and not all(_zeroish(v) for v in f.values())]
                if not rows:
                    continue
                if len(r) == 1:
                    txt = ', '.join(f"{k}={_cell(v)}" for k, v in list(rows[0].items())[:4])
                elif len(r) <= 4 and not ch.get('result_total_rows'):
                    txt = ' | '.join(', '.join(f"{k}={_cell(v)}" for k, v in list(x.items())[:3]) for x in rows)
                else:
                    key = next((k for k in _NAME_KEYS if k in rows[0]), next(iter(rows[0])))
                    txt = f"{ch.get('result_total_rows', len(r))} rows, e.g. " + '; '.join(_cell(x.get(key, '')) for x in rows[:3])
            elif isinstance(r, list):
                continue                     # bare arrays are trend series
            else:
                if _zeroish(r):
                    continue
                txt = _cell(r)
            out.append(f"- {title}{' ' + st if st else ''}: {txt}")
        if out:
            lines.append(s['section'].lstrip('# '))
            lines += out
    return '\n'.join(lines)

# ── DIGEST ───────────────────────────────────────────────────────────────────
def write_digest(F, E, rd, c, path):
    L = [f"# Collection digest ({datetime.date.today()})", '',
         f"Hosts {F['hosts']} (FullStack {F['hosts_fullstack']}, Infra {F['hosts_infra']}); services {F['services']:,}; "
         f"PGs {F['process_groups']:,}; requests/day {F['traces_per_day']}; problems {F['problems_per_week']}/week "
         f"({F['problems_per_day']}/day avg, {E['problems_last_24h']} last 24h)",
         f"Infra-only by host group: {E['infra_by_host_group']}",
         f"Tags: hosts {E['hosts_tagged']}, services {E['services_tagged']}; host groups {F['host_groups']}; IP-named hosts {F['hosts_ip_named']}",
         f"Top problem sources: {F['top_problem_sources'][:4]}",
         f"Top services 7d: {E['top_services_7d'][:5]}", '',
         '## Alerting and zones',
         f"Profiles {F['alerting_profiles']}, notifications {F['notifications_count']} ({F['notifications_enabled']} enabled), workflows {F['workflow_count']}",
         f"No severity rules: {F['alerting_profiles_no_rules']}", f"Test profiles live: {F['alerting_profiles_test']}",
         f"Profiles with no notification: {E['profiles_without_notification']}",
         f"MZ issues: {F['mz_issues']}", f"Custom segments: {F['custom_segment_count']}",
         f"Metric events: {E['metric_events']}", (f"Classic cloud metric events (data not checkable in Grail): raised Davis events in 30d (live) "
          f"{E.get('metric_events_cloud_fired', [])}; no events in 30d (quiet or no data, unverified) "
          f"{E.get('metric_events_cloud_quiet', [])}"),
         f"Anomaly detectors: {E['anomaly_detectors']}",
         f"SLOs: classic {F['classic_slo_count']} ({E['classic_slo_templated']} templated), Gen3 {F['slo_count'] if F['slo_count'] is not None else 'NOT READABLE'}",
         f"Duplicate workflows: {E.get('workflows_duplicated', [])}", '',
         '## Logs (1-hour sample x 24)',
         f"~{human(F['log_records_24h'])}/day; no host {F.get('log_unattributed_pct')}%; forwarder {F.get('log_external_pct')}%; "
         f"OneAgent log-to-trace {F.get('log_to_trace_pct')}%; PGs logging {F['pg_with_logs_pct']}%",
         f"Sources: {F['log_sources']}", f"Forwarder log groups/hour: {E.get('forwarder_top_log_groups_per_hour', [])}",
         f"Log buckets (retention days): {E['log_buckets']}", '',
         '## Cloud, VMware, K8s',
         f"Cloud metric namespaces: {E['cloud_metric_namespaces']}",
         f"Gen3 connections: AWS {E['gen3_aws_connections']}, Azure {E['gen3_azure_connections']}, GCP {E['gen3_gcp_connections']}",
         f"Cloud instances: {F['cloud_hosts_running']} running servers, {F['cloud_hosts_without_oneagent']} without OneAgent {F['cloud_hosts_without_oneagent_names'][:5]}; Azure {E['azure_vms']}",
         f"VMware: {F.get('vmware_hosts', 0)} ESXi, {F.get('vmware_vms', 0)} VMs; {E.get('vmware_prod_vms', 'n/a')}; prod gap by prefix {E.get('vmware_prod_gap_by_prefix', {})}",
         f"K8s clusters {F['cloud_k8s_clusters']}; synthetics {F['synthetic_monitors']}; Grail RUM {F['grail_rum_active']}; classic RUM rules {F['rum_apps_classic']}; DB extensions {F['db_extensions_present']}", '',
         *tech_discovery.digest_lines(F, E), '',
         '## Anomaly candidates (judge before using)',
         f"Failure rate rising (name, prior%, now%, vol/wk): {E['failrate_rising']}",
         f"Failure rate chronic >=80% both weeks: {E['failrate_chronic']}",
         f"Hot persistent hosts (avg, p95): {E['cpu_hot_persistent']}",
         f"Problem burst: {E.get('problem_burst', 'none')}", '',
         f"Generic services: {F['generic_services']}"]
    if rd:
        L += ['', '## Gen2/Gen3 readiness (attention items only)', rd]
    if c.errors or c.warnings:
        L += ['', '## Errors and warnings'] + [f"- {x}" for x in c.errors + c.warnings]
    open(path, 'w', encoding='utf-8').write('\n'.join(L) + '\n')

if __name__ == '__main__':
    ap_ = argparse.ArgumentParser(description='dt-value-roadmap-v2 data collection')
    ap_.add_argument('--context', required=True)
    ap_.add_argument('--out', required=True, help='Output directory')
    ap_.add_argument('--readiness', action='store_true', help='Also run dt-upgrade-readiness (~2 min)')
    ap_.add_argument('--prod-prefixes', default='p', help='Comma list of VM name prefixes that mean production')
    ap_.add_argument('--vdi', default='vdi', help='Regex for Azure VDI desktops to exclude')
    ap_.add_argument('--ephemeral', default='worker|databricks|workerenv', help='Regex for batch hosts excluded from CPU checks')
    a = ap_.parse_args()
    os.makedirs(a.out, exist_ok=True)
    c = Collector(a.context, a.out)
    F, E = collect(c, a)
    rd = readiness(c, a.context) if a.readiness else None
    F['collected'] = str(datetime.date.today())
    F['_evidence'] = E
    if c.errors:
        F['_errors'] = c.errors
    json.dump(F, open(os.path.join(a.out, 'facts.json'), 'w', encoding='utf-8'), indent=1, default=str)
    write_digest(F, E, rd, c, os.path.join(a.out, 'digest.md'))
    print(f"facts.json and digest.md written to {a.out} ({len(c.errors)} errors, {len(c.warnings)} warnings)")
