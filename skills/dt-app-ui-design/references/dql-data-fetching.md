# DQL Data-Fetching Conventions

**Base hook:** `@dynatrace-sdk/react-hooks` `useDql`

**`useDql` call signature** — confirmed against `@dynatrace-sdk/react-hooks` ^1.6.0:
- Accepts `useDql(query: string | DqlQueryParams)` where `DqlQueryParams` is `{ query: string }` — no `body` wrapper
- There is NO built-in `fetchInterval` parameter — TypeScript error if used
- Returns `{ data, isLoading, error, refetch, cancel, ... }` — use `refetch()` for manual refresh

**For simple fixed-interval refresh (no user-controlled picker)** — use `useEffect` + `setInterval` directly in the hook:

```ts
const { data, isLoading, error, refetch } = useDql({ query: QUERY });

useEffect(() => {
  const id = setInterval(() => void refetch(), 60_000);
  return () => clearInterval(id);
}, []); // refetch is stable from the SDK
```

**For app-wide user-controlled refresh picker** — use this shim so one `setRefreshInterval(ms)` call drives all live queries:

```ts
// hooks/useDqlLive.ts
import { useDql } from '@dynatrace-sdk/react-hooks';
import { useEffect, useSyncExternalStore } from 'react';

let interval = 0;
const listeners = new Set<() => void>();

export function setRefreshInterval(ms: number) {
  interval = ms;
  listeners.forEach(fn => fn());
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function useDqlLive<T>(query: string) {
  const ms = useSyncExternalStore(subscribe, () => interval);
  const result = useDql<T>({ query });

  useEffect(() => {
    if (!ms) return;
    const id = setInterval(() => void result.refetch(), ms);
    return () => clearInterval(id);
  }, [ms]); // refetch is stable from the SDK

  return result;
}
```

**Query organization:**
- Build all query strings in `lib/` helper functions — never inline DQL in components
- One function per logical query; pass time range and filter params as arguments

**Timeseries buffer + trim** — stabilize ingest-lag artifacts:

```ts
// Add 5m lead, drop first 5 + last 2 buckets
const from = expandFrom(timeRange.from, 5);
const raw = await runQuery(buildCostQuery(from, timeRange.to));
return trimSeries(raw, { head: 5, tail: 2 });
```

**Loading state:** drive from `useDql`'s `loading` boolean — never infer loading from empty records (empty records can mean no data, not loading).

For DQL syntax: load `dt-dql-essentials`.
