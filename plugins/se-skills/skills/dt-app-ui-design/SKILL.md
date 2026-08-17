---
name: dt-app-ui-design
description: Design system and UI patterns for Dynatrace AppEngine custom apps (dt-app). Covers strato component choices, layout primitives, color token rules, stat tile patterns, table/list patterns, custom SVG visualization, and DQL data-fetching conventions. Load when building or modifying any dt-app custom app UI — regardless of use case or layout.
---

# Dynatrace Custom App UI Design

Reference implementation: [github.com/mattrein-dt/tokenomics](https://github.com/mattrein-dt/tokenomics). Patterns below apply to any dt-app regardless of domain.

---

## 1. App shell (required for every app)

Every app must wrap in this structure — `AppRoot` is the strato theme provider; skipping it breaks all color tokens and component styles.

```tsx
// main.tsx
import { AppRoot } from '@dynatrace/strato-components';
import { BrowserRouter } from 'react-router-dom';

<AppRoot>
  <BrowserRouter basename="ui">
    <App />
  </BrowserRouter>
</AppRoot>
```

```tsx
// App.tsx — page shell + routing
import { Page } from '@dynatrace/strato-components-preview';
import { Routes, Route } from 'react-router-dom';

<Page>
  <Page.Header><Header /></Page.Header>
  <Page.Main>
    <Routes>
      <Route path="/" element={<MainPage />} />
      {/* add routes as needed */}
    </Routes>
  </Page.Main>
</Page>
```

```tsx
// Header.tsx — nav bar
import { AppHeader } from '@dynatrace/strato-components-preview';
import { Link } from 'react-router-dom';

<AppHeader>
  <AppHeader.Navigation>
    <AppHeader.Logo as={Link} to="/" />
    <AppHeader.NavigationItem as={Link} to="/data">Query explorer</AppHeader.NavigationItem>
  </AppHeader.Navigation>
</AppHeader>
```

---

## 2. Color and theming rules

**Structural colors** — always use design tokens, never hardcode hex:

```ts
// Colors is a DEFAULT import — named import { Colors } fails to compile
import Colors from '@dynatrace/strato-design-tokens/colors';

// Surfaces
Colors.Background.Base.Default            // page background (darkest)
Colors.Background.Surface.Default         // card/panel surface — elevated above Base
Colors.Background.Container.Neutral.Default  // stat tile / muted container — elevated above Surface
Colors.Background.Container.Primary.Default  // selected row / active state

// Text
Colors.Text.Neutral.Default
Colors.Text.Primary.Default

// Borders
Colors.Border.Neutral.Default
Colors.Border.Primary.Default

// Accents
Colors.Theme.Primary["70"]    // primary brand accent (sparkline strokes, links)
Colors.Theme.Neutral["60"]    // muted accent

// Status
Colors.Text.Critical.Default                   // error text
Colors.Background.Container.Critical.Accent    // alert highlight background
```

**Dark theme contrast — use JS tokens, not CSS vars, for structure:**

The DT dark theme has near-zero contrast between several CSS custom properties:
- `var(--dt-color-background-base-secondary)` is visually identical to the page background
- `var(--dt-color-border-default)` is too subtle for progress bar tracks or panel container backgrounds

**Rule:** For any element that must be visibly distinct (section panels, dividers, progress bar tracks), always use the JS `Colors` object. It resolves to computed hex values at build time. CSS vars are fine for text color, cursor, and other properties where subtle contrast is acceptable.

**Surface hierarchy that creates visible elevation in dark mode:**
```
Colors.Background.Base.Default                  // canvas / page
  └─ Colors.Background.Surface.Default          // section panels, cards  ← use for sections
       └─ Colors.Background.Container.Neutral.Default  // tiles, progress tracks  ← use for inline containers
```

Never use `var(--dt-color-background-base-secondary)` as a panel background — it is indistinct from the page in dark mode. Use `Colors.Background.Surface.Default` instead.

**Data-channel colors** — define as named module-level constants, not tokens. Each data dimension gets its own channel; never reuse a structural token color for a data series:

```ts
// lib/colors.ts — example set, adjust per app domain
export const COST_COLOR   = 'rgb(120, 145, 180)';  // slate-blue
export const MARGIN_COLOR = 'hsl(150, 55%, 45%)';  // emerald
export const VOLUME_COLOR = 'rgb(90, 140, 210)';   // blue
export const WARN_COLOR   = 'hsl(28, 85%, 55%)';   // amber

// Color ramps for continuous scales: pure math, independent of tokens
export function efficiencyColor(t: number): string {
  // 0 = good (emerald), 1 = bad (orange)
  const hue = 150 - t * 130;
  const sat = 55 + t * 30;
  const lit = 45 + t * 6;
  return `hsl(${hue}, ${sat}%, ${lit}%)`;
}

export function heatColor(t: number): string {
  // 0 = cool (slate-blue), 1 = hot (amber) — RGB lerp
  const r = Math.round(120 + t * 115);
  const g = Math.round(145 + t * 5);
  const b = Math.round(180 - t * 135);
  return `rgb(${r}, ${g}, ${b})`;
}
```

---

## 3. Layout primitives

**Primary layout unit:** `<Flex>` from `@dynatrace/strato-components`.

```tsx
// Page content column
<Flex flexDirection="column" gap={12} padding={16}>...</Flex>

// Toolbar / controls row
<Flex justifyContent="space-between" alignItems="center" gap={16} flexWrap="wrap">
  <Flex gap={8} alignItems="center">
    {/* left controls */}
  </Flex>
  <Flex gap={8}>
    {/* right controls */}
  </Flex>
</Flex>

// Two-panel split with animated collapse
// flex-basis transition drives the collapse/expand (250ms ease)
<Flex gap={0} alignItems="stretch" style={{ minWidth: 1100 }}>
  <div style={{ flexBasis: leftCollapsed ? '0%' : '50%', overflow: 'hidden', transition: 'flex-basis 250ms ease' }}>
    {/* left panel — visualization */}
  </div>
  <CollapseDivider collapsed={leftCollapsed} onToggle={setLeftCollapsed} />
  <div style={{ flexBasis: leftCollapsed ? '100%' : '50%', transition: 'flex-basis 250ms ease' }}>
    {/* right panel — list/table */}
  </div>
</Flex>
```

**Stat tiles row** — raw flex, not `<Flex>`, so tiles reflow on narrow viewports:

```tsx
<div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
  {/* tiles — see section 4 */}
</div>
```

**Settings overlay** — absolutely positioned, not a modal, so it doesn't interrupt page flow:

```tsx
<div style={{ position: 'absolute', top: 48, right: 16, zIndex: 10, background: Colors.Background.Surface.Default, borderRadius: 8, padding: 16, border: `1px solid ${Colors.Border.Neutral.Default}` }}>
  {/* settings content */}
</div>
```

---

## 4. Stat tiles (top info bar)

Use `SingleValue` + `SingleValue.Sparkline` from `@dynatrace/strato-components-preview`. Wrap in a raw `<div>` (not a strato card) for flex reflow.

```tsx
// SingleValue lives in the /charts sub-path, not the root preview package
import { SingleValue } from '@dynatrace/strato-components-preview/charts';
import Colors from '@dynatrace/strato-design-tokens/colors';
import { COST_COLOR } from '../lib/colors';

<div style={{
  background: Colors.Background.Container.Neutral.Default,
  border: `1px solid ${Colors.Border.Neutral.Default}`,
  borderRadius: 8,
  padding: '12px 16px',
  flex: '1 1 200px',
  height: 116,
}}>
  <SingleValue
    label="Cost / 1M tokens"
    data={value}         // string | number — NOT nullable, null causes TS error
    loading={isLoading}  // skeleton shows when true regardless of data value
  >
    <SingleValue.Sparkline
      data={trendTimeseries}  // Timeseries type — omit entirely if no time-series data
      variant="area"
      color={COST_COLOR}
      curve="smooth"
    />
  </SingleValue>
</div>
```

Rules:
- Always pass `loading` — prevents layout shift while data arrives
- `data` is `string | number` — never pass `null` (TypeScript error). Pass the current value and let `loading={true}` show the skeleton
- Sparkline is optional — omit `SingleValue.Sparkline` entirely for point-in-time values (counts, statuses)
- Sparkline color = the data-channel constant for that metric, never a structural token

---

## 5. Tables and lists

**Choose based on whether rows need to align with an adjacent visualization:**
- **`DataTable`** (from `@dynatrace/strato-components-preview/tables`): use when the table stands alone. Gives sorting, row actions, empty state, and accessibility for free.
- **CSS Grid rows**: use only when row heights must align pixel-precisely with an adjacent visualization panel (e.g., a side-by-side Smartscape graph where each row maps to a graph node).

CSS Grid row pattern — when alignment with a visualization is required:

```tsx
const COLS = '"minmax(140px, 1fr) minmax(180px, 230px) 95px 70px"';
const ROW_HEIGHT = 76;  // match any adjacent visualization's row height

// Header row
<div style={{ display: 'grid', gridTemplateColumns: COLS, padding: '0 8px' }}>
  <Th label="Service" sortKey="name" sort={sort} onSort={setSort} />
  <Th label="Trend" />
  <Th label="$ / 1M tok" sortKey="cost" sort={sort} onSort={setSort} />
  <Th label="% of cost" sortKey="pct" sort={sort} onSort={setSort} />
</div>

// Data row
<div style={{
  display: 'grid',
  gridTemplateColumns: COLS,
  height: ROW_HEIGHT,
  alignItems: 'center',
  padding: '0 8px',
  background: selected ? Colors.Background.Container.Primary.Default : 'transparent',
}}>
  <span>{service.name}</span>
  <InlineSparkline data={service.trend} />   {/* custom SVG — see section 6 */}
  <span>{formatUsd(service.costPerMTok)}</span>
  <span>{formatPct(service.pctOfTotal)}</span>
</div>
```

**Sort state** — three-click cycling (desc → asc → natural):

```ts
type SortState = { key: string; dir: 'asc' | 'desc' } | null;

function nextSort(current: SortState, key: string): SortState {
  if (current?.key !== key) return { key, dir: 'desc' };
  if (current.dir === 'desc') return { key, dir: 'asc' };
  return null;  // back to natural order
}
```

**Loading cells:** `<SkeletonText>` from `@dynatrace/strato-components` per cell — not a full-row spinner.

---

## 6. Custom SVG visualizations

**When to use raw SVG vs. strato charts:**
- Raw SVG: topology/graph layouts, per-row inline sparklines, any viz needing pixel control or animation
- Strato `TimeseriesChart`: standalone time-series panels, DQL explorer views

**Sizing and responsiveness:**

```tsx
const ref = useRef<HTMLDivElement>(null);
const [width, setWidth] = useState(0);

useEffect(() => {
  const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
  if (ref.current) ro.observe(ref.current);
  return () => ro.disconnect();
}, []);

<div ref={ref} style={{ width: '100%' }}>
  <svg width={width} height={svgHeight}>
    {/* content */}
  </svg>
</div>
```

**Zoom + pan:**

```tsx
<svg onMouseDown={startPan} onWheel={onZoom}>
  <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
    {/* zoomable content */}
  </g>
</svg>
```

**Tooltips** — absolutely positioned in the wrapper div, not SVG `<title>`:

```tsx
<div style={{ position: 'relative' }}>
  <svg ...>
    {/* nodes/edges */}
  </svg>
  {tooltip && (
    <div style={{
      position: 'absolute',
      top: tooltip.y,
      // anchor left or right based on cursor position to avoid overflow
      ...(tooltip.x > width / 2
        ? { right: width - tooltip.x + 12 }
        : { left: tooltip.x + 12 }),
      background: Colors.Background.Surface.Default,
      border: `1px solid ${Colors.Border.Neutral.Default}`,
      borderRadius: 6,
      padding: '6px 10px',
      zIndex: 5,
    }}>
      {tooltip.content}
    </div>
  )}
</div>
```

**Inline sparkline (table rows):**

```tsx
// Custom SVG sparkline component
function Sparkline({ data, forecast, width = 180, height = 40 }) {
  const xs = data.map((_, i) => (i / (data.length - 1)) * width * HISTORY_FRACTION);
  const yScale = (v: number) => height - ((v - min) / (max - min)) * height;
  const pts = data.map((v, i) => `${xs[i]},${yScale(v)}`).join(' ');

  return (
    <svg width={width} height={height}>
      <polyline
        points={pts}
        fill="none"
        stroke={Colors.Theme.Primary["70"]}
        strokeWidth={1.4}
      />
      {forecast && (
        <>
          {/* confidence band */}
          <path d={bandPath(forecast)} fill={Colors.Theme.Primary["70"]} opacity={0.14} />
          {/* median forecast line */}
          <polyline points={forecastPts} fill="none"
            stroke={Colors.Theme.Primary["70"]} strokeWidth={1.4}
            strokeDasharray="3 2.5" />
        </>
      )}
    </svg>
  );
}
```

Reserve a `HISTORY_FRACTION` (e.g., 0.75) of x-axis width for history so "now" aligns across all rows.

---

## 7. DQL data-fetching conventions

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

---

## 8. Required `app.config.json` scopes

Always include `storage:buckets:read` alongside any table-specific scope. Without it, Grail queries silently return 0 records with no thrown error — a very common gotcha.

```json
{
  "scopes": [
    { "name": "storage:buckets:read",  "comment": "Required for all bucket-partitioned Grail tables (metrics, logs, spans, events)" },
    { "name": "storage:metrics:read",  "comment": "Add only if querying metrics" },
    { "name": "storage:logs:read",     "comment": "Add only if querying logs" },
    { "name": "storage:spans:read",    "comment": "Add only if querying spans/traces" },
    { "name": "storage:events:read",   "comment": "Add only if querying events" },
    { "name": "environment-api:entities:read",  "comment": "For entity queries and Smartscape" },
    { "name": "environment-api:problems:read",  "comment": "For Davis problems" }
  ]
}
```

Only add scopes the app actually uses — the user is prompted to approve scopes on first load; unnecessary scopes increase friction and audit surface.

For diagnosing the silent-0-records failure (including how to read `metadata.grail.notifications`): load `dt-appengine-iam`.
