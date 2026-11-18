---
name: table
description: DraftForge data tables with TanStack Table. Use when showing rows of records (lists with columns, admin queues, logs, stats) or touching DataTable, ColumnDef, or a *Table.tsx component.
---

# DraftForge Data Tables

Tabular data renders through the generic `DataTable` in `frontend/app/components/ui/data-table/`
(TanStack Table v8 on top of the shadcn `ui/table` primitives). Each domain gets one reusable
`<Domain>Table` that owns its columns; pages and cards only pass data and callbacks.

Reference implementation: `frontend/app/components/opsnotices/OpsNoticeTable.tsx`.
Brand rule ("tables use `DataTable`"): `docs/theming-guide/ai/references/component-substitutions.md#tables` via the `brand` skill.

## Layout

| Piece | Where | Owns |
|---|---|---|
| `DataTable` | `components/ui/data-table/DataTable.tsx` | row model, single-column sorting, empty row, `meta` classes, test ids |
| `DataTableColumnHeader` | same folder | sortable header button + `aria-sort` icon |
| `<Domain>Table` | `components/<domain>/<Domain>Table.tsx` | columns, badges, links, action buttons, default sort |

Don't render `<table>`, `ui/table` primitives, or flex "rows" directly for record lists.
Existing raw tables are legacy; migrate one when you substantially touch it.

## Writing a domain table

1. Build columns with `createColumnHelper<T>()` in a module-level `buildColumns(options)`;
   call it inside `useMemo` keyed on the options. Never inline a new `columns` array per render.
2. Always pass `getRowId` (the record's id as a string). Index ids break sorting and React keys.
3. Optional columns (an Event column hidden on an event page, an actions column only when
   `onResolve` is given) are props on the domain table, not copies of it.
4. Function accessors need an `id` (`col.accessor(fn, { id: 'last_seen' })`).
5. Actions use brand buttons (`SecondaryButton size="sm"`, `ConfirmButton` in dialogs),
   with a `data-testid` per row action. Never a raw `<button>`.
6. Severity, state and category render as `Badge`s with a fixed variant map, not ad-hoc colours.

## Sorting

- Sorting is **opt-in per column** (`enableSorting: true`); `DataTable` disables it by default and
  turns multi-sort off, so a header click always sorts by that column alone.
- Need a tie-break (severity then recency)? Put it in that column's `sortingFn`, don't use
  multi-column initial sorting.
- Numeric accessors sort descending first; set `sortDescFirst` explicitly so intent is visible.
- Header for a sortable column: `header: ({ column }) => <DataTableColumnHeader column={column} title="Last seen" />`.

## Cells, wrapping and mobile

- Cells are `whitespace-nowrap`; the `ui/table` container scrolls horizontally on narrow screens.
  That is the mobile strategy: never squeeze columns with `flex-1` rows.
- Give the one free-text column room to wrap: `meta: { cellClassName: 'min-w-40 whitespace-normal wrap-anywhere' }`.
  Use `wrap-anywhere`, not `break-words`: only `overflow-wrap: anywhere` lowers a table column's
  min-content width, so one long token (an id, a snake_case key) can't stretch the column.
- Numbers: `meta: { headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' }`.
- Secondary text uses `text-muted-foreground`; surfaces and borders come from tokens (`border-border`).

## Empty and loading

- `emptyMessage` renders a single full-width row. Cards that should vanish when empty return
  `null` before rendering the table (see `OpsNoticesCard`).
- Loading and error states stay in the parent (query owner), not in `DataTable`.

## Test ids

- `data-testid` on the table, `rowTestId={(r) => \`<domain>-row-${r.id}\`}` for rows.
- Sort buttons expose `data-table-sort-<columnId>`.

## Tests

Vitest + Testing Library, jsdom. Cover per domain table: default order, each optional column
on/off, per-row actions (shown only where allowed, disabled while pending), one header re-sort,
empty message. `DataTable` itself is covered in `ui/data-table/__tests__/DataTable.test.tsx`.

## Pitfalls

- `data` from a query: pass it straight through; don't map it into a new array each render.
- `ColumnMeta` is augmented in `DataTable.tsx` (`headerClassName`, `cellClassName`); add new
  meta fields there, not by casting.
- Server-side paging/sorting: add `manualPagination`/`manualSorting` plus counts to `DataTable`
  as props when the first table needs it; don't fork the component.
