# Choosing a visualization for every tile

Every notebook and dashboard tile gets an explicit visualization, chosen from the shape of its result. A tile left on a default
or sent as raw records is the weakest way to show a finding. `build_assets.py` holds the choices in one registry (`NB_TILES` for
the notebook, the `data(...)` calls for the dashboard) and `--test-queries` checks each result against its choice.

## First rule: the document must carry its schema version

A tile only opens in its saved visualization when the notebook or dashboard content carries the schema version the UI writes.
Generated notebooks without it opened every tile as **Raw response**, even with `visualization: table` stored on the tile. Adding
`version: "7"` to the notebook content fixed it (confirmed in a tenant: tables, bar charts, donuts and a pie opened as saved). In one
tenant all 34 saved notebooks use `"7"`, as a string. Dashboards use an integer, 21 for most of that tenant's dashboards.
`build_assets.py` reads the most common value from the exported documents and falls back to those defaults.

Do not embed cached query results to try to force a view: a synthesized result made a tile show `[object Object]`. The tile settings
and the version are enough.

## Pick by shape

| Result shape | Visualization | Notes |
|---|---|---|
| One row of numbers | `singleValue` | One row only. Color only numeric fields. |
| One category column and one or two numeric columns, up to about 15 rows | `categoricalBarChart` | Comparisons: this window against a week earlier, ranked lists. Set `categoryAxis` and `valueAxis` explicitly. |
| One category column and one numeric column, parts of a whole, 8 categories or fewer | `pieChart` or `donutChart` | Shares only (cost centers, usage classes, query sources). Never for values that do not add up. |
| A time series (array column with `timeframe` and `interval`) | `barChart` for daily or coarse buckets, `lineChart` or `areaChart` for fine buckets | The query must come from `timeseries` or `makeTimeseries`. |
| Many columns, mixed text and numbers, change percentages, timestamps | `table` | Detail views and anything people will sort or filter. |

Rules that follow from this:
1. **Pair a chart with a table when both help.** The chart shows the comparison at a glance; the table keeps the change percentage,
   timestamps and the long tail. Example: top metrics as a bar chart of 15, then the table of 25 with change.
2. **Shape the query for the chart, not the other way round.** A category chart needs exactly one text column. Build a single label
   column (for example `concat(source, " / ", type)`) and drop other text columns, timestamps and percentages from the chart query.
   Keep those in the table variant.
3. **Percentages and counts do not share an axis.** Leave `Change %` out of a bar chart that plots datapoints.
4. **Cap the categories.** Use `limit 10` to `limit 15` for bar charts and 8 or fewer for pie charts. The table shows the rest.
5. **Long names go on the category axis of a bar chart**, never in a pie legend with more than a few slices.
6. **Use the same visualization settings shape the UI writes.** For a category bar chart:
   `chartSettings: {categoricalBarChartSettings: {categoryAxis: [field], valueAxis: [fields]}}`. Tables and pies use `chartSettings: {}`.
   A time series chart gets `chartSettings: {legend: {position: bottom, showLegend: true}}`.
7. **Set `autoSelectVisualization: false`** so the choice is kept when the notebook reopens.

## What this skill uses

| Tile | Visualization |
|---|---|
| Billed datapoints by data type and source | table |
| Billed datapoints per day | barChart |
| Datapoints by source and type, last 24h against a week earlier | categoricalBarChart, plus a table with change |
| Top metrics, last 24h against a week earlier | categoricalBarChart (15), plus a table (25) with change |
| Share of datapoints by how the metric is used | donutChart |
| Never or rarely queried, still arriving | table |
| Heaviest histogram bucket series | categoricalBarChart |
| Share of metric queries by source | donutChart, plus a table with scan and failures |
| Billed datapoints by cost center | pieChart |
| Detectors by alerts opened | categoricalBarChart, plus a table with last alert time |
| Dashboard: selected window against 7 days earlier | singleValue (with green and red change coloring), lineChart overlay, categoricalBarChart by source and top metrics, tables with change coloring |

## Checks before applying

1. `build_assets.py --test-queries` runs every tile and reports `SHAPE PROBLEM` for a result that does not suit its visualization
   (a category chart with two text columns, a time series chart with no array, a single value with several rows). Fix each one.
2. After applying, export the notebook and confirm `content.version` is present, then (`dtctl get notebook <id> -o yaml --plain`, decode the byte-array `content`) and confirm every
   section's `state.visualization` matches the registry.
3. Ask the user to open it. Saved settings cannot show how a tile looks, and when a user adjusts tiles the saved file shows only the final
   choice, so ask what they changed rather than inferring it from a diff.
4. When the user changes a visualization, update the registry to match so the next run starts from their choice.
