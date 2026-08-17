---
name: dt-dashboard-variables
description: Dynatrace dashboard variable authoring - the complete pattern for multi-select query variables, the GUID wildcard "select all" sentinel, in(field, array($Var)) filter syntax, cascading variables, and why isNull() guards break variable filtering. Also covers two DQL gotchas that surface only in dashboard tile queries: the space required in "by: {" and fields that become inaccessible after "expand".
---

# Dynatrace Dashboard Variables

Use alongside the `dtctl` skill when building or debugging dashboards with variables.

## Variable YAML structure

```yaml
content:
  variables:
    - key: environment          # referenced in queries as $environment
      type: query               # always "query" for dynamic lists; "static" has no auto-select
      multiple: true            # enables multi-select; required for the wildcard default
      editable: true
      visible: true
      version: 2
      defaultValue:
        - 3420b2ac-f1cf-4b24-b62d-61ba1ba8ed05*   # GUID wildcard — see below
      input: |
        fetch spans, from:now()-6h
        | filter isNotNull(`k8s.namespace.annotation.gaig/environment`)
        | summarize cnt = count(), by: {environment = `k8s.namespace.annotation.gaig/environment`}
        | fields environment
        | sort environment asc
```

### The GUID wildcard — "select all" default

`3420b2ac-f1cf-4b24-b62d-61ba1ba8ed05*` is Dynatrace's system sentinel for "select all".
When the dashboard loads with this as the default, the platform strips the `in()` filter
entirely server-side, so every record passes. It is NOT a real value in the data.

- Use it as `defaultValue` on any `multiple: true` query variable to get a working "select all"
  on first load without hardcoding values.
- Never use `type: static` with an "All" option and string comparison — variable injection
  in DQL is via `in()` array expansion, not string equality, so `$env == "All"` never works.

### Cascading variables

A variable's `input` query can reference earlier variables with `$VarName`. The variable
re-executes whenever the referenced variable changes:

```yaml
- key: service
  input: |
    fetch spans, from:now()-6h
    | filter in(`k8s.namespace.annotation.gaig/environment`, array($environment))
    | summarize cnt = count(), by: {service = dt.service.name}
    | fields service
```

Define variables in dependency order (the variable being referenced must appear first in the list).

## Filtering tile queries with variables

Use `in(field, array($VarName))` — this is the only reliable pattern:

```dql
fetch spans, from:now()-2h
| filter in(`k8s.namespace.annotation.gaig/environment`, array($environment))
| filter in(dt.service.name, array($service))
```

When the GUID wildcard default is active, the platform removes the `in()` predicate
server-side and all records are returned. When the user selects specific values,
`in()` filters to exactly those values.

### Do NOT use isNull() as a fallback guard

```dql
-- WRONG: passes ALL records where the field is null, regardless of what the user selected
| filter in(`k8s.namespace.annotation.gaig/environment`, array($environment))
  or isNull(`k8s.namespace.annotation.gaig/environment`)

-- RIGHT: let the wildcard sentinel handle "show all" — no isNull() needed
| filter in(`k8s.namespace.annotation.gaig/environment`, array($environment))
```

The `or isNull()` pattern looks safe but silently bypasses the variable filter for every
record that lacks the field (e.g. CloudFoundry spans when only k8s environments are listed).
It makes the variable appear to work while actually returning a superset.

## Mixing platforms with OR clauses

When data spans multiple platforms that use different environment fields, add explicit OR
branches BEFORE any `expand` step (see expand section below):

```dql
fetch spans, from:now()-2h
| filter in(`k8s.namespace.annotation.gaig/environment`, array($environment))
  or (`cloudfoundry.space.name` == "prod"    and in("Production",  array($environment)))
  or (`cloudfoundry.space.name` == "preprod" and (in("Development", array($environment))
                                               or in("UAT",         array($environment))))
```

This maps CF space names to the k8s environment vocabulary so a single variable controls both
platforms. Any k8s environment with no CF analog simply has no CF OR branch.

---

## DQL gotchas that surface in dashboard tiles

### 1. `summarize` requires a space in `by: {`

```dql
-- PARSE_ERROR (no space before brace)
| summarize cnt = count(), by:{field}

-- CORRECT
| summarize cnt = count(), by: {field}
```

The aggregation result must also be aliased when `by:` is present:

```dql
-- FIELD_DOES_NOT_EXIST at runtime (unaliased count with by:)
| summarize count(), by: {field}

-- CORRECT
| summarize cnt = count(), by: {field}
```

### 2. Some fields become inaccessible after `expand`

`expand events = span.events` unrolls an array into rows. After the expand, certain
platform-specific fields (`cloudfoundry.space.name` is the confirmed case) return
`FIELD_DOES_NOT_EXIST` even though they were present before the expand. The fix is to
alias them into a new field BEFORE the expand:

```dql
fetch spans, from:now()-2h
| filter ...                                  -- filters can still reference the field here
| fieldsAdd cf_space = `cloudfoundry.space.name`   -- capture BEFORE expand
| expand events = span.events
| filter isNotNull(events[exception.type])
| fieldsAdd environment = coalesce(`k8s.namespace.annotation.gaig/environment`, cf_space)
```

The alias `cf_space` survives the expand and is accessible in all subsequent steps.
The same pattern applies to any field that becomes inaccessible post-expand — alias it first.
