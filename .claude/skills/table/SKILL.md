---
name: table
description: DraftForge data tables with TanStack Table v9. Use when showing rows of records (lists with columns, admin queues, logs, stats) or touching DataTable, AppColumnDef, make*Columns, or a *Table.tsx component.
---

# DraftForge Data Tables

Record lists render through the shared `DataTable` (`frontend/app/components/ui/data-table/`,
TanStack Table **v9** on the shadcn `ui/table` primitives): one shared table, one column
factory per record type, one thin `<Domain>Table` reused everywhere that type is listed.

Worked example: `components/opsnotices/` (`opsNoticeColumns.tsx` + `OpsNoticeTable.tsx`).
Brand rule ("lists use `DataTable`"): `docs/theming-guide/ai/references/component-substitutions.md#tables`.

## The three layers

| Layer | File | Owns |
|---|---|---|
| `DataTable` | `ui/data-table/DataTable.tsx` | feature set, sorting, filtering + toolbar, pagination (hidden when it fits), striping, row click, empty row, `table-fixed` layout, `scrollX` |
| `make<Domain>Columns(options)` | `components/<domain>/<domain>Columns.tsx` | every column def, keyed by a `<Domain>ColumnId` union, plus `DEFAULT_<DOMAIN>_COLUMNS` |
| `<Domain>Table` | `components/<domain>/<Domain>Table.tsx` | `useMemo` over the factory, `getRowId`, test-id prefix, default sort |

Callers pick columns by id (`columns={['severity', 'summary', 'actions']}`), never re-column per
page. Need another column? Add it to the factory's union.

## TanStack v9 specifics

- Features are registered explicitly in `appTableFeatures` (`tableFeatures({...})` in
  `DataTable.tsx`). An API that's `undefined` at runtime means its feature isn't listed there.
  Add a feature (filtering, faceting, grouping, selection) there, opt-in, when a table needs it.
- Types carry the feature set: use `AppColumnDef<Row>`, `AppColumn<Row>`, `AppRow<Row>` from
  `~/components/ui/data-table`, never TanStack's bare `ColumnDef` / `Column` / `Row`.
- Column `meta` is typed by `metaHelper` in the feature set (no `declare module`):
  `headClassName`, `cellClassName`, `headTestId`.
- Custom sort is `sortFn` (v8's `sortingFn`): `(rowA, rowB, columnId) => number`.
- Read state from `table.state`, not `table.getState()`.

## Layout: fit first, scroll by opt-in

- Default is `table-fixed`: the table never scrolls sideways. Secondary columns take fixed
  widths (`meta: { headClassName: 'w-24', cellClassName: 'w-24' }`); **one** main column has no
  width and absorbs the rest. Cells wrap (`whitespace-normal break-words`).
- On small screens, hide secondary columns with `hidden sm:table-cell` / `md:` / `lg:` on BOTH
  `headClassName` and `cellClassName`. `DataTable` reads those classes (`isCellRendered`) so the
  empty row spans only what is rendered.
- Don't lose the hidden data: stack it under the main cell for phones
  (`<span className="text-xs text-muted-foreground md:hidden">`).
- Long unbroken tokens (ids, keys) in the main column: `wrap-anywhere`.
- `scrollX` keeps every column, sizes to content and scrolls in a `ScrollFrame` (focusable
  region, `scrollLabel`, right-edge fade). Use it only when every column must stay visible.

## Columns

- Sortable header: `header: ({ column }) => <DataTableColumnHeader column={column} title="Last seen" />`.
  Clicks follow TanStack's order (first direction from `sortDescFirst`, numbers default to
  descending), then unsorted. A plain-string header isn't sortable; also set `enableSorting: false`.
- Single-column sort only. A tie-break (severity, then recency) is that column's `sortFn`.
- Numbers: `text-right tabular-nums`. Secondary text: `text-muted-foreground`.
- States/categories are `Badge`s with a fixed variant map.
- Cell actions are brand buttons (`SecondaryButton size="sm" className="min-h-11 sm:min-h-8"`),
  call `e.stopPropagation()` so they don't fire `onRowClick`, and carry `${prefix}-<action>-<id>`.
  Inline text links in cells are exempt from the 44px floor; the row is the touch target.
- More than one action per row, or rows whose actions differ: `DataTableRowActions`. When the
  table has room (a wide page or full-screen dialog), pass `inlineFrom="md"`: from that breakpoint
  the actions are inline `SecondaryButton`s (`color="red"` when destructive) in a `role="group"`,
  and below it only a ⋮ menu renders, never both. Size the actions column for the inline buttons
  from the breakpoint (`w-16 sm:w-14 md:w-96`). Without `inlineFrom` it is always the menu.
  `aria-label` "Actions for <name>" and `${prefix}-actions-<id>` sit on the group or the trigger;
  each button or item is `${prefix}-<action>-<id>`. Keep a disabled action shown with its `hint`
  (menu text, or a tooltip plus `aria-describedby` inline) rather than hiding it. Tests switch
  modes with `setViewportWidth` from `ui/data-table/__tests__/viewport.ts`.
  Worked example: `components/team/manage/rosterColumns.tsx`.
- Table-level actions ("Add …") and a count go on `toolbarActions` / `toolbarStart`
  (`${prefix}-actions` bar), which works without `enableToolbar`.

## Test ids

`<Domain>Table` takes `testIdPrefix` (default the domain): table `${prefix}-table`, rows
`${prefix}-row-<id>`, actions `${prefix}-<action>-<id>`. Sort buttons are
`data-table-sort-<columnId>`; pagination `data-table-prev` / `data-table-next`.

## Tests (vitest + Testing Library, jsdom)

Per domain table: default order, a custom `columns` list, test-id prefix, row actions (only
where allowed, disabled while pending, don't trigger row click), one header re-sort, the
stacked mobile line, empty message. `DataTable` itself: `ui/data-table/__tests__/DataTable.test.tsx`.
jsdom has no `matchMedia`; `useMediaQuery` returns `false`, so every breakpoint reads "small"
unless a test calls `setViewportWidth(px)` (restore it after).

## Filters (`enableToolbar`)

The toolbar (`DataTableToolbar.tsx`) builds itself from column `meta`; nothing renders unless a
column opts in or a search is given. Domain tables expose it as one prop (`OpsNoticeTable filters`).

| Want | Column / prop | Notes |
|---|---|---|
| Multi-select filter with live counts | `filterFn: 'oneOf'` + `meta.filterLabel: 'Severity'` | Facets are the column's **accessor values**, so faceted columns must return the display value (a string), not a sort rank; put ranking in `sortFn`. `meta.facetLabel(v)` relabels, `meta.facetOrder` orders options; `null`/`''` show as "Not set". |
| Show/hide a column | `meta.columnLabel: 'Event'` | Columns without it can't be hidden. |
| Client-side search | `globalSearch={{ placeholder }}` | TanStack global filter (`includesString`) over string columns. |
| Server/page search | `search={{ value, onChange }}` | Page owns the state; replaces `globalSearch`. |
| Start filtered | `initialColumnFilters`, `initialColumnVisibility` | Uncontrolled. |

- Active selections show as removable chips (`RemoveIconButton`), and **Reset** clears filters and search.
  An all-filtered-out table shows `emptyFilteredMessage`.
- Below `sm` the controls move into a **Filters** sheet; search and chips stay on the bar.
- Test ids use `toolbarTestIdPrefix` (domain tables pass their `testIdPrefix`):
  `${p}-toolbar`, `${p}-search`, `${p}-facet-trigger-<col>`, `${p}-facet-option-<col>-<slug>`,
  `${p}-filter-chip-<col>-<slug>`, `${p}-filter-chip-remove-…`, `${p}-filters-reset`,
  `${p}-columns-trigger`, `${p}-columns-option-<col>`, `${p}-filters-sheet-trigger`.
- jsdom tests that open a facet need `ResizeObserver` and `Element.prototype.scrollIntoView`
  stubs (the command list uses both); see `DataTableToolbar.test.tsx`.

## Not built yet

Group-by, controlled/URL state, a table title, fill-height layouts. Add each as an opt-in prop
so existing tables don't change; new features go into `appTableFeatures`.
