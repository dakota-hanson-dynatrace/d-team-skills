#!/usr/bin/env python3
"""
dt-value-roadmap-v2: technology and extension opportunity discovery.

Looks at what a tenant already collects (DB spans, messaging spans, process technologies, log sources,
metric namespaces, outbound ports) and maps it to Dynatrace Hub extensions, then compares with what is
already installed and configured. Everything is read-only and runs sequentially through dtctl.

Used two ways:
  - imported by collect.py:  discover(c, F, E)
  - standalone test run:     python tech_discovery.py --context "<ctx>" --out <dir>

Output (F = facts, E = evidence):
  F['tech_opportunities']  list of dicts, one per detected technology
  F['tech_summary']        counts by status
  E['tech_*']              raw probe results for the model to judge
"""
import argparse, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Each rule: label, category, and the signals that identify it.
#   db      : db.system values on spans           msg  : messaging.system values on spans
#   proc    : OneAgent software-technology types  log  : regex on log.source
#   metric  : regex on metric key namespace       ext  : regex on installed extension ids
#   hub     : regex on Hub catalog names/ids (what Dynatrace offers)
#   kind    : 'server' = a product the customer runs (extension can monitor it);
#             'device' = network/security appliance (no agent, extension via ActiveGate)
RULES = [
    dict(label='Oracle Database', cat='Database', db=['oracle'], proc=['ORACLE_DATABASE', 'ORACLE_DB_LISTENER'],
         ext=r'sql-oracle|oracle', hub=r'^oracle database|oracle db|sql-oracle', kind='server'),
    dict(label='MySQL', cat='Database', db=['mysql', 'mariadb'], proc=['MYSQL', 'MARIADB'], ext=r'mysql',
         hub=r'mysql|mariadb', kind='server'),
    dict(label='PostgreSQL', cat='Database', db=['postgresql', 'postgres'], proc=['POSTGRE_SQL'], ext=r'postgres',
         hub=r'postgres', kind='server'),
    dict(label='Microsoft SQL Server', cat='Database', db=['mssql', 'microsoft.sql_server'], proc=['MSSQL_CLIENT', 'MICROSOFT_SQL_SERVER'], flowing=r'^sql-server', metric=r'^sql-server',
         ext=r'sql-server|mssql', hub=r'sql server', kind='server'),
    dict(label='IBM Db2', cat='Database', db=['db2'], ext=r'db2', hub=r'db2', kind='server'),
    dict(label='MongoDB', cat='Database', db=['mongodb'], ext=r'mongo', hub=r'mongo', kind='server'),
    dict(label='Redis', cat='Cache', db=['redis'], ext=r'redis', hub=r'^redis|redis', kind='server'),
    dict(label='Cassandra', cat='Database', db=['cassandra'], ext=r'cassandra', hub=r'cassandra', kind='server'),
    dict(label='Elasticsearch / OpenSearch', cat='Search', db=['elasticsearch', 'opensearch'], proc=['ELASTIC_SEARCH'],
         log=r'elasticsearch|opensearch', ext=r'elasticsearch|opensearch', hub=r'elasticsearch|opensearch', kind='server'),
    dict(label='Apache Solr', cat='Search', proc=['APACHE_SOLR'], log=r'(^|[/\\])solr', metric=r'^legacy\.solr',
         ext=r'solr', hub=r'solr', kind='server'),
    dict(label='Apache Kafka', cat='Messaging', msg=['kafka'], proc=['APACHE_KAFKA'], log=r'kafka|zookeeper',
         metric=r'^legacy\.kafka|^kafka', ext=r'kafka', hub=r'kafka', kind='server'),
    dict(label='RabbitMQ', cat='Messaging', msg=['rabbitmq'], log=r'rabbitmq', ext=r'rabbitmq', hub=r'rabbitmq', kind='server'),
    dict(label='ActiveMQ / Artemis', cat='Messaging', msg=['activemq', 'artemis'], proc=['ACTIVEMQ_CLIENT', 'ACTIVE_MQ'], metric=r'^(artemis|activeMQ)$',
         ext=r'activemq|artemis', hub=r'activemq|artemis', kind='server'),
    dict(label='IBM MQ', cat='Messaging', msg=['ibmmq', 'ibm_mq', 'websphere_mq'], ext=r'ibm-?mq', hub=r'ibm mq|websphere mq', kind='server'),
    dict(label='NGINX', cat='Web / proxy', proc=['NGINX'], log=r'nginx', ext=r'nginx', hub=r'nginx', kind='server'),
    dict(label='HAProxy', cat='Web / proxy', proc=['HAPROXY'], log=r'haproxy', ext=r'haproxy', hub=r'haproxy', kind='server'),
    dict(label='Apache HTTP Server', cat='Web / proxy', proc=['APACHE_HTTP_SERVER'], ext=r'apache-?http|httpd',
         hub=r'apache http|httpd', kind='server'),
    dict(label='Oracle HTTP Server', cat='Web / proxy', log=r'/ohs/|ohs1', ext=r'oracle-?http|ohs', hub=r'oracle http', kind='server'),
    dict(label='Microsoft IIS', cat='Web / proxy', proc=['IIS', 'IIS_APP_POOL'], ext=r'\biis\b|-iis|iis-', hub=r'\biis\b', kind='server'),
    dict(label='Oracle WebLogic', cat='App server', proc=['ORACLE_WEBLOGIC'], msg=['weblogic'], log=r'weblogic',
         metric=r'^legacy\.weblogic', ext=r'weblogic', hub=r'weblogic', kind='server'),
    dict(label='JBoss / WildFly', cat='App server', proc=['JBOSS', 'WILDFLY'], metric=r'^legacy\.jboss|^jboss',
         ext=r'jboss|wildfly', hub=r'jboss|wildfly', kind='server'),
    dict(label='IBM WebSphere', cat='App server', proc=['WEBSPHERE', 'WEBSPHERE_LIBERTY'], log=r'websphere', ext=r'websphere|liberty',
         hub=r'websphere|liberty', kind='server'),
    dict(label='Apache Tomcat (JMX)', cat='App server', proc=['APACHE_TOMCAT'], metric=r'^legacy\.tomcat', ext=r'tomcat',
         hub=r'tomcat', kind='server'),
    dict(label='webMethods Integration Server', cat='Integration', msg=['sag_webmethods_is'], proc=['SAG_WEBMETHODS_IS'],
         log=r'webmethods', ext=r'webmethods', hub=r'webmethods', kind='server'),
    dict(label='SAP Commerce (Hybris)', cat='Application', proc=['SAP_HYBRIS'], log=r'hybris', ext=r'hybris', hub=r'hybris', kind='server'),
    dict(label='Argo CD', cat='Platform tooling', metric=r'^argocd', log=r'^argocd', ext=r'argo', hub=r'argo', kind='server'),
    dict(label='cert-manager', cat='Platform tooling', metric=r'^certmanager', ext=r'cert-?manager', hub=r'cert-?manager', kind='server'),
    dict(label='Istio / Envoy service mesh', cat='Platform tooling', proc=['ISTIO', 'ENVOY'], log=r'istio', ext=r'istio|envoy',
         hub=r'istio|envoy', kind='server'),
    dict(label='Microsoft Active Directory / Windows DNS', cat='Identity / infrastructure', log=r'^DNS Server$|active.?directory', metric=r'^active-directory',
         flowing=r'^active-directory', ext=r'active-?directory', hub=r'active directory', kind='server'),
    dict(label='Databricks', cat='Data platform', metric=r'^databricks', flowing=r'^databricks', ext=r'databricks', hub=r'databricks', kind='server'),
    dict(label='Cloudflare', cat='Network / security', metric=r'^cloudflare', flowing=r'^cloudflare', ext=r'cloudflare', hub=r'cloudflare', kind='device'),
    dict(label='SonarQube', cat='Platform tooling', metric=r'^sonarqube', flowing=r'^sonarqube', ext=r'sonar', hub=r'sonar', kind='server'),
    dict(label='Illumio (segmentation)', cat='Network / security', log=r'illumio', ext=r'illumio', hub=r'illumio', kind='device'),
    dict(label='Oracle Enterprise Manager / Grid Infrastructure', cat='Database', log=r'/oracle/gc_inst|crsdata|oracle\.ahf|emoms', ext=r'oracle', hub=r'oracle enterprise|oracle em|grid', kind='server'),
    dict(label='Sonatype Nexus', cat='Platform tooling', log=r'nexus', ext=r'nexus', hub=r'nexus', kind='server'),
    dict(label='Liferay', cat='Application', log=r'liferay', ext=r'liferay', hub=r'liferay', kind='server'),
    dict(label='PHP-FPM', cat='App server', proc=['PHP_FPM'], ext=r'php', hub=r'php', kind='server'),
    dict(label='Palo Alto Networks (Cortex XDR / firewall)', cat='Network / security', log=r'/traps/|cortex|pan-?os|paloalto|palo[ _-]?alto|globalprotect',
         ext=r'palo', hub=r'palo alto', kind='device'),
    dict(label='Prisma Cloud / Twistlock', cat='Network / security', log=r'twistlock|prisma', ext=r'prisma|twistlock', hub=r'prisma|twistlock', kind='device'),
    dict(label='F5 BIG-IP', cat='Network / security', log=r'\bf5\b|big-?ip|bigip|\bltm\b', metric=r'^f5', ext=r'f5|bigip', hub=r'f5|big-?ip', kind='device'),
    dict(label='Fortinet FortiGate', cat='Network / security', log=r'forti(gate|net)', ext=r'forti', hub=r'forti', kind='device'),
    dict(label='Cisco devices (SNMP)', cat='Network / security', log=r'cisco|%asa|asa-', ext=r'cisco', hub=r'cisco', kind='device'),
    dict(label='Citrix NetScaler', cat='Network / security', log=r'netscaler|citrix', ext=r'netscaler|citrix', hub=r'netscaler|citrix', kind='device'),
    dict(label='Check Point / Juniper / Arista', cat='Network / security', log=r'checkpoint|juniper|junos|arista', ext=r'checkpoint|juniper|arista',
         hub=r'check ?point|juniper|arista', kind='device'),
    dict(label='Generic syslog / SNMP traps', cat='Network / security', log=r'syslog|snmp', flowing=r'^snmp_auto', ext=r'snmp', hub=r'snmp traps|snmp', kind='device'),
]

# Weak, port-only hints for outbound client spans that did not carry db/messaging attributes.
PORT_HINTS = {1433: 'SQL Server', 1521: 'Oracle Database', 3306: 'MySQL', 5432: 'PostgreSQL', 6379: 'Redis',
              9092: 'Apache Kafka', 5672: 'RabbitMQ', 27017: 'MongoDB', 9200: 'Elasticsearch', 389: 'LDAP', 636: 'LDAPS',
              25: 'SMTP', 1414: 'IBM MQ', 8983: 'Apache Solr', 9042: 'Cassandra', 50000: 'IBM Db2'}


def human(n):
    n = float(n)
    for div, suf in ((1e9, 'B'), (1e6, 'M'), (1e3, 'K')):
        if n >= div:
            v = n / div
            return f"{v:.1f}".rstrip('0').rstrip('.') + suf if v < 100 else f"{v:.0f}{suf}"
    return f"{n:.0f}"


def plural(n, one, many=None):
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


def volume_label(calls, log_records, ninst):
    """Trace calls are the headline volume; logs and process counts are fallbacks, each with its own unit."""
    if calls:
        return f"{human(calls)} calls/hr"
    if log_records:
        return f"{human(log_records)} log records/hr"
    if ninst:
        return plural(ninst, 'process instance')
    return 'metrics only'


def rank_key(t):
    """Same-unit comparisons only: technologies with trace calls rank first (by calls), then log-only, then process-only."""
    calls, logs, inst = t.get('calls') or 0, t.get('log_records') or 0, t.get('instances') or 0
    tier = 0 if calls else 1 if logs else 2 if inst else 3
    return (tier, -(calls or logs or inst), t['technology'])


# Statuses that mean the customer already has (or is getting) the extension: never shown as an opportunity.
NOT_OPPORTUNITY = ('Extension installed and configured', 'Extension installed, configuration state unreadable', 'Extension data already flowing',
                   'Extension installed, no monitoring configuration', 'Extension installed, all configurations disabled',
                   'Detected, no matching Hub extension found')

# The deck slide is skipped when there are this many opportunities or fewer (the report always lists them).
SLIDE_MIN_EXCLUSIVE = 3

# Customer-facing groups for the deck slide (the report keeps the finer category).
GROUPS = [('Databases and data', ('Database', 'Cache', 'Search', 'Data platform')),
          ('Messaging and integration', ('Messaging', 'Integration')),
          ('Infrastructure and security', None)]   # None = everything else


def group_of(category):
    for name, cats in GROUPS:
        if cats and category in cats:
            return name
    return GROUPS[-1][0]


def extension_opportunities(data):
    """Detected technologies with a Hub extension that is not installed. Ranked by trace calls, then log volume, then process count."""
    skip = set(data.get('tech_exclude', []))
    opp = [t for t in data.get('tech_opportunities', []) if t.get('status') not in NOT_OPPORTUNITY and t.get('hub_candidates')
           and t['technology'] not in skip]
    return sorted(opp, key=rank_key)


SPAN_WINDOW_MIN, SPAN_SCALE = 15, 4   # 1-hour span scans hit the Grail scan cap on big tenants; sample 15 minutes and scale


def short_hub(h):
    return {'id': h.get('id'), 'name': h.get('name')}


def discover(c, F, E):
    """Run the probes, build F['tech_opportunities']. Every probe is a separate sequential dtctl call."""
    # 1. DB systems on spans
    db = c.q('tech_db_systems', f'fetch spans, from:-{SPAN_WINDOW_MIN}m | filter isNotNull(db.system) or isNotNull(db.system.name) '
                                '| fieldsAdd s=coalesce(db.system.name, db.system) | summarize calls=count(), by:{s} | sort calls desc | limit 40')
    db_calls = {str(r.get('s')).lower(): int(float(r.get('calls') or 0)) * SPAN_SCALE for r in db if r.get('s')}
    # 2. Messaging systems on spans
    ms = c.q('tech_messaging', f'fetch spans, from:-{SPAN_WINDOW_MIN}m | filter isNotNull(messaging.system) | summarize calls=count(), by:{{messaging.system}} '
                               '| sort calls desc | limit 30')
    msg_calls = {str(r.get('messaging.system')).lower(): int(float(r.get('calls') or 0)) * SPAN_SCALE for r in ms}
    # 3. Software technologies on process group instances (library "clients" are filtered by rule, not here)
    pr = c.q('tech_process_types', 'fetch dt.entity.process_group_instance, from:-24h | fieldsAdd t=softwareTechnologies | expand t '
                                   '| fieldsAdd ts=toString(t) | parse ts, "\'type:\' LD:tech \',\'" | summarize instances=count(), by:{tech} '
                                   '| sort instances desc | limit 200')
    proc = {str(r.get('tech')): int(float(r.get('instances') or 0)) for r in pr if r.get('tech')}
    # 4. Log sources (1-hour window, same reason as the log-health queries: 24h scans hit the scan cap)
    ls = c.q('tech_log_sources', 'fetch logs, from:-1h | summarize n=count(), by:{log.source} | sort n desc | limit 300')
    logs = [(str(r.get('log.source')), int(float(r.get('n') or 0))) for r in ls if r.get('log.source')]
    # 5. Metric namespaces: first token (split on . or _) of every key not in the built-in dt.*/cloud.* families
    mt = c.q('tech_metric_ns', 'fetch metric.series, from:-24h | filter not startsWith(metric.key, "dt.") and not startsWith(metric.key, "cloud.") '
                               '| fieldsAdd p=splitString(metric.key, ".") | fieldsAdd ns=if(p[0] == "legacy", concat("legacy.", p[1]), else: p[0]) '
                               '| summarize keys=countDistinctExact(metric.key), by:{ns} | sort keys desc | limit 400')
    metrics = {str(r.get('ns')): int(float(r.get('keys') or 0)) for r in mt if r.get('ns')}
    # 6. Outbound client calls by port, excluding plain web ports and anything already typed as DB/messaging
    pt = c.q('tech_ports', f'fetch spans, from:-{SPAN_WINDOW_MIN}m | filter span.kind == "client" and isNotNull(server.port) and isNull(db.system) and isNull(messaging.system) '
                           '| summarize calls=count(), hosts=countDistinct(server.address), by:{server.port} | sort calls desc | limit 60')
    ports = {int(float(r['server.port'])): (int(float(r['calls'] or 0)) * SPAN_SCALE, int(float(r['hosts'] or 0))) for r in pt if r.get('server.port') is not None}
    # 7. Hub catalog, installed extensions, and their monitoring configurations
    hub = c.get('tech_hub', 'hub-extensions') or []
    inst_raw = c.get('tech_installed', 'extensions')
    inst_known = inst_raw is not None
    inst_ids = [i.get('extensionName', '') for i in (inst_raw or [])]

    results = []
    for r in RULES:
        ev, strength, calls, logrec, ninst = [], 0, 0, 0, 0
        for k in r.get('db', []):
            if k in db_calls:
                ev.append(f"DB spans: {db_calls[k]:,} calls/hr (db.system={k})"); strength = max(strength, 3); calls += db_calls[k]
        for k in r.get('msg', []):
            if k in msg_calls:
                ev.append(f"Messaging spans: {msg_calls[k]:,} calls/hr (messaging.system={k})"); strength = max(strength, 3); calls += msg_calls[k]
        for k in r.get('proc', []):
            if k in proc:
                ev.append(f"OneAgent detected {k} on {plural(proc[k], 'process instance')}"); strength = max(strength, 3); ninst = max(ninst, proc[k])
        if r.get('log'):
            pat = re.compile(r['log'], re.I)
            hit = [(s, n) for s, n in logs if pat.search(s)]
            if hit:
                ev.append(f"Log sources: {', '.join(s for s, _ in hit[:3])} ({sum(n for _, n in hit):,} records/hr)"); strength = max(strength, 2); logrec += sum(n for _, n in hit)
        if r.get('metric'):
            pat = re.compile(r['metric'])
            hit = [(k, n) for k, n in metrics.items() if pat.search(k)]
            if hit:
                ev.append(f"Metric namespace: {', '.join(k for k, _ in hit[:3])} ({sum(n for _, n in hit)} metrics)"); strength = max(strength, 2)
        if not ev:
            continue
        ext_pat = re.compile(r['ext'], re.I) if r.get('ext') else None
        installed = [i for i in inst_ids if ext_pat and ext_pat.search(i)]
        hub_pat = re.compile(r['hub'], re.I) if r.get('hub') else None
        cands = [short_hub(h) for h in hub if hub_pat and (hub_pat.search(h.get('name') or '') or hub_pat.search(h.get('id') or ''))][:4]
        flow = bool(r.get('flowing')) and (any(re.search(r['flowing'], k) for k in metrics) or any(re.search(r['flowing'], x, re.I) for x, _ in logs))
        results.append(dict(flowing=flow, technology=r['label'], category=r['cat'], kind=r['kind'], confidence={3: 'High', 2: 'Medium', 1: 'Low'}[strength],
                            evidence=ev, calls=calls, log_records=logrec, instances=ninst,
                            volume_label=volume_label(calls, logrec, ninst), installed_extensions=installed, hub_candidates=cands))

    # Configs for installed extensions that matched something (sequential; one dtctl call each)
    cfg_cache = {}
    for t in results:
        n = total = 0
        unreadable = False
        for e in t['installed_extensions']:
            if e not in cfg_cache:
                cfgs = c.get(f"tech_cfg_{e.split('.')[-1]}", 'extension-configs', e)
                cfg_cache[e] = ((len(cfgs), sum(1 for g in cfgs if (g.get('value') or {}).get('enabled'))) if cfgs is not None else None)
            if cfg_cache[e] is None:
                unreadable = True
            else:
                total += cfg_cache[e][0]; n += cfg_cache[e][1]
        t['active_configs'], t['total_configs'] = n, total
        if t['flowing']:
            t['status'] = 'Extension data already flowing'
        elif t['installed_extensions'] and n:
            t['status'] = 'Extension installed and configured'
        elif t['installed_extensions'] and unreadable and not n:
            t['status'] = 'Extension installed, configuration state unreadable'
        elif t['installed_extensions'] and total:
            t['status'] = 'Extension installed, all configurations disabled'
        elif t['installed_extensions']:
            t['status'] = 'Extension installed, no monitoring configuration'
        elif t['hub_candidates'] and not inst_known:
            t['status'] = 'Opportunity (install state unreadable, needs extensions:definitions:read)'
        elif t['hub_candidates']:
            t['status'] = 'Opportunity: extension available in Hub'
        else:
            t['status'] = 'Detected, no matching Hub extension found'

    # Port-only hints (low confidence), skipping ports already explained by a typed detection
    seen = {t['technology'] for t in results}
    hints = []
    for p, (calls, hosts) in sorted(ports.items(), key=lambda x: -x[1][0]):
        if p in PORT_HINTS and PORT_HINTS[p] not in seen:
            hints.append(f"port {p} ({PORT_HINTS[p]}): {calls:,} calls/hr to {hosts} destinations, no db/messaging attributes on the span")

    order = {'Opportunity: extension available in Hub': 0, 'Extension installed, no monitoring configuration': 1,
             'Extension installed, all configurations disabled': 1, 'Opportunity (install state unreadable, needs extensions:definitions:read)': 0,
             'Extension data already flowing': 4, 'Extension installed, configuration state unreadable': 1,
             'Detected, no matching Hub extension found': 2, 'Extension installed and configured': 3}
    results.sort(key=lambda t: (order[t['status']], {'High': 0, 'Medium': 1, 'Low': 2}[t['confidence']], t['technology']))
    F['tech_opportunities'] = results
    F['tech_summary'] = {s: sum(1 for t in results if t['status'] == s) for s in order}
    E['tech_installed_extensions'] = inst_ids if inst_known else 'UNREADABLE (403)'
    E['tech_port_hints'] = hints
    E['tech_unmatched_process_types'] = sorted(k for k in proc if not any(k in r.get('proc', []) for r in RULES))[:100]
    E['tech_unmatched_log_sources'] = [s for s, _ in logs if not any(r.get('log') and re.search(r['log'], s, re.I) for r in RULES)][:60]
    E['tech_hub_catalog_size'] = len(hub)
    return F, E


def digest_lines(F, E):
    L = ['## Technology and extension opportunities',
         f"Status counts: {F.get('tech_summary')}; Hub catalog size {E.get('tech_hub_catalog_size')}; installed extensions {E.get('tech_installed_extensions') if isinstance(E.get('tech_installed_extensions'), str) else len(E.get('tech_installed_extensions', []))}"]
    for t in F.get('tech_opportunities', []):
        hub = '; '.join(h['name'] for h in t['hub_candidates']) or 'none'
        L.append(f"- [{t['status']}] {t['technology']} ({t['category']}, {t['confidence']}): {' | '.join(t['evidence'])}. "
                 f"Installed: {t['installed_extensions'] or 'none'} (enabled configs {t['active_configs']} of {t['total_configs']}). Hub: {hub}")
    if E.get('tech_port_hints'):
        L.append('Port-only hints (low confidence): ' + '; '.join(E['tech_port_hints'][:6]))
    L.append(f"Unmatched OneAgent technologies: {E.get('tech_unmatched_process_types', [])[:25]}")
    L.append(f"Unmatched log sources (top): {E.get('tech_unmatched_log_sources', [])[:15]}")
    return L


if __name__ == '__main__':
    import collect
    ap = argparse.ArgumentParser(description='Technology and extension opportunity discovery (standalone test run)')
    ap.add_argument('--context', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    c = collect.Collector(a.context, a.out)
    F, E = discover(c, {}, {})
    json.dump({'F': F, 'E': E, 'errors': c.errors, 'warnings': c.warnings}, open(os.path.join(a.out, 'tech.json'), 'w', encoding='utf-8'), indent=1)
    open(os.path.join(a.out, 'tech_digest.md'), 'w', encoding='utf-8').write('\n'.join(digest_lines(F, E)) + '\n')
    print(f"{len(F['tech_opportunities'])} technologies detected, {len(c.errors)} errors, {len(c.warnings)} warnings")
