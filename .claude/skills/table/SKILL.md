---
name: table
description: DraftForge data tables with TanStack Table. Use when showing rows of records (lists with columns, admin queues, logs, stats) or touching DataTable, AppColumnDef, make*Columns, or a *Table.tsx component.
---

# DraftForge Data Tables

Record lists render through the shared `DataTable` (`frontend/app/components/ui/data-table/`,
TanStack Table v8 on the shadcn `ui/table` primitives): one shared table,
one column factory per record type, one thin `<Domain>Table` reused everywhere that type is listed.

Worked example: `components/opsnotices/` (`opsNoticeColumns.tsx` + `OpsNoticeTable.tsx`).
Brand rule ("lists use `DataTable`"): `docs/theming-guide/ai/references/component-substitutions.md#tables`.

## The three layers

| Layer | File | Owns |
|---|---|---|
| `DataTable` | `ui/data-table/DataTable.tsx` | sorting, pagination (hidden when it fits), striping, row click, empty row, `table-fixed` layout, `scrollX` |
| `make<Domain>Columns(options)` | `components/<domain>/<domain>Columns.tsx` | every column def, keyed by a `<Domain>ColumnId` union, plus `DEFAULT_<DOMAIN>_COLUMNS` |
| `<Domain>Table` | `components/<domain>/<Domain>Table.tsx` | `useMemo` over the factory, `getRowId`, test-id prefix, default sort |

Callers pick columns by id (`columns={['severity', 'summary', 'actions']}`), never re-column per
page. Need another column? Add it to the factory's union.

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

- Type them as `AppColumnDef<Row>[]`, not TanStack's `ColumnDef`.
- `meta`: `headClassName`, `cellClassName`, `headTestId` (augmented in `DataTable.tsx`; add new
  meta fields there).
- Sortable header: `header: ({ column }) => <DataTableColumnHeader column={column} title="Last seen" />`.
  Clicks follow TanStack's order (first direction from `sortDescFirst`, numbers default to
  descending), then unsorted. A plain-string header isn't sortable; also set `enableSorting: false`.
- Single-column sort only. A tie-break (severity, then recency) is that column's `sortingFn`.
- Numbers: `text-right tabular-nums`. Secondary text: `text-muted-foreground`.
- States/categories are `Badge`s with a fixed variant map.
- Cell actions are brand buttons (`SecondaryButton size="sm" className="min-h-11 sm:min-h-8"`),
  call `e.stopPropagation()` so they don't fire `onRowClick`, and carry `${prefix}-<action>-<id>`.
  Inline text links in cells are exempt from the 44px floor; the row is the touch target.

## Test ids

`<Domain>Table` takes `testIdPrefix` (default the domain): table `${prefix}-table`, rows
`${prefix}-row-<id>`, actions `${prefix}-<action>-<id>`. Sort buttons are
`data-table-sort-<columnId>`; pagination `data-table-prev` / `data-table-next`.

## Tests (vitest + Testing Library, jsdom)

Per domain table: default order, a custom `columns` list, test-id prefix, row actions (only
where allowed, disabled while pending, don't trigger row click), one header re-sort, the
stacked mobile line, empty message. `DataTable` itself: `ui/data-table/__tests__/DataTable.test.tsx`.
jsdom has no `matchMedia`; `useMediaQuery` returns `false`, so every breakpoint reads "small".

## Not built yet

Toolbar (faceted filters, group-by), column visibility, controlled/URL state, `title` tab,
`fillHeight`. Add each as an opt-in prop when a table needs it, so
existing tables don't change.
