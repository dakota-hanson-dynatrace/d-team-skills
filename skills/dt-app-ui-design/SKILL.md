---
name: dt-app-ui-design
description: Design system and UI patterns for Dynatrace AppEngine custom apps (dt-app). Covers strato component choices, layout primitives, color token rules, stat tile patterns, table/list patterns, custom SVG visualization, and DQL data-fetching conventions. Load when building or modifying any dt-app custom app UI — regardless of use case or layout.
---

# Dynatrace Custom App UI Design

Reference implementation: [github.com/mattrein-dt/tokenomics](https://github.com/mattrein-dt/tokenomics). Patterns below apply to any dt-app regardless of domain.

Foundational rules below (app shell, color tokens, required scopes) apply to every app.
For the specific piece you're building, also read:
- **Layout, stat tiles, tables, or custom SVG viz** → `references/layout-and-components.md`
- **Fetching data with `useDql` / DQL conventions** → `references/dql-data-fetching.md`

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

## 3. Required `app.config.json` scopes

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
