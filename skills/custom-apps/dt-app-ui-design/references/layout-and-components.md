# Layout, Stat Tiles, Tables, and Custom SVG

## Layout primitives

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
  {/* tiles — see Stat Tiles below */}
</div>
```

**Settings overlay** — absolutely positioned, not a modal, so it doesn't interrupt page flow:

```tsx
<div style={{ position: 'absolute', top: 48, right: 16, zIndex: 10, background: Colors.Background.Surface.Default, borderRadius: 8, padding: 16, border: `1px solid ${Colors.Border.Neutral.Default}` }}>
  {/* settings content */}
</div>
```

---

## Stat tiles (top info bar)

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

## Tables and lists

**Choose based on whether rows need to align with an adjacent visualization:**
- **`DataTable`** (from `@dynatrace/strato-components-preview/tables`): use when the table stands alone. Gives sorting, row actions, empty state, and accessibility for free.
- **CSS Grid rows**: use only when row heights must align pixel-precisely with an adjacent visualization panel (e.g., a side-by-side Smartscape graph where each row maps to a graph node).

**`DataTable` column widths — use `fr`, not px, with `fullWidth`:**

A column's `width` accepts a plain pixel number, a fraction string (`` `${number}fr` ``), `'auto'`, or `'content'`. With `fullWidth` set on the table, plain px-number widths are **not** stretched to fill the container — the grid just leaves the remainder as blank space past the last column. Give every column an `'Nfr'` width instead, sized proportionally to what the px widths would've been (a column that would've been 260px becomes `'26fr'`, one that would've been 90px becomes `'9fr'`), so the full set of columns always fills the available width:

```tsx
columns={[
  { id: 'name', header: 'Host', accessor: 'name', width: '26fr' as const },
  { id: 'cpu', header: 'CPU', accessor: 'cpuPct', width: '14fr' as const, cell: ({ value }) => <UsageCell value={Number(value)} /> },
]}
```

Gotcha: in an array mixing column-def object literals of different shapes (some with `cell`, some without), TypeScript widens `width: '26fr'` to plain `string`, which then fails against `DataTableColumnDef`'s `` `${number}fr` `` union — add `as const` to every fr-width literal to keep it narrow. This specific error only surfaces during the real `dt-app build` / `dt-app deploy` compile step; a standalone `tsc -p ui/tsconfig.json --noEmit` run did not catch it. Don't treat a table page as done until it's actually built or deployed, not just type-checked in isolation.

Also: an accessor for a flat row key that contains a literal dot (e.g. a DQL field like `'k8s.node.name'`) must be a function — `(r) => r['k8s.node.name']` — not the bare string `'k8s.node.name'`. A dotted string accessor gets split into a nested object path (`row.k8s.node.name`), which is `undefined` on a flat row whose key literally contains dots, and renders a blank cell instead of erroring.

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
  <InlineSparkline data={service.trend} />   {/* custom SVG — see below */}
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

## Custom SVG visualizations

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
