import type { Column, ReactTable, RowData } from '@tanstack/react-table';
import { Check, ChevronDown, Columns3, SlidersHorizontal } from 'lucide-react';
import { useId, useMemo, useState, type ReactNode } from 'react';

import { Badge } from '~/components/ui/badge';
import { Button } from '~/components/ui/button';
import { RemoveIconButton, SecondaryButton } from '~/components/ui/buttons';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '~/components/ui/command';
import { Input } from '~/components/ui/input';
import { Label } from '~/components/ui/label';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '~/components/ui/sheet';
import { useMediaQuery } from '~/hooks/useMediaQuery';
import { cn } from '~/lib/utils';

// Type-only: DataTable imports this file as a value, so a value import back would be a cycle.
import type { AppFeatures } from './DataTable';

/** Absent cell values once stringified; all three show as one "Not set" option. */
const ABSENT = new Set(['null', 'undefined', '']);

export function facetSlug(value: string): string {
  if (ABSENT.has(value)) return 'none';
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

/** Column meta the toolbar reads. A column opts in per control. */
export interface ToolbarColumnMeta {
  /** Faceted multi-select filter with live counts, e.g. "Severity". Pair with `filterFn: 'oneOf'`. */
  filterLabel?: string;
  /** Listed (and hideable) in the Columns menu under this name. */
  columnLabel?: string;
  /** Display text for a raw facet value (defaults to the value, "Not set" when absent). */
  facetLabel?: (value: string) => string;
  /** Option order by raw value (e.g. severity high to low); unlisted values follow alphabetically. */
  facetOrder?: readonly string[];
}

function toolbarMeta(columnDef: { meta?: unknown }): ToolbarColumnMeta {
  return (columnDef.meta ?? {}) as ToolbarColumnMeta;
}

function labelFor(meta: ToolbarColumnMeta, value: string): string {
  if (ABSENT.has(value)) return 'Not set';
  return meta.facetLabel?.(value) ?? value;
}

/** Search owned by the page (server-side or custom), rendered in the toolbar. */
export interface DataTableSearch {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  label?: string;
}

/** Client-side search across every string column, via TanStack's global filter. */
export interface DataTableGlobalSearch {
  placeholder?: string;
  label?: string;
}

/** Below this width the filter controls move into a Sheet. */
export const TABLE_TOOLBAR_MOBILE_QUERY = '(max-width: 639.98px)';

const TRIGGER_CLASS =
  'min-h-11 w-full justify-between font-normal sm:min-h-8 sm:w-44';

function ToolbarField({
  htmlFor,
  label,
  children,
  className,
}: {
  htmlFor: string;
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex min-w-0 flex-col gap-1', className)}>
      <Label
        htmlFor={htmlFor}
        className="text-xs font-normal text-muted-foreground"
      >
        {label}
      </Label>
      {children}
    </div>
  );
}

function CheckMark({ checked }: { checked: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        'flex size-4 shrink-0 items-center justify-center rounded-sm border border-primary',
        checked
          ? 'bg-primary text-primary-foreground'
          : 'opacity-50 [&_svg]:invisible',
      )}
    >
      <Check className="size-3 text-primary-foreground" />
    </span>
  );
}

export function DataTableFacetedFilter<TData extends RowData>({
  column,
  label,
  triggerId,
  testIdPrefix,
}: {
  column: Column<AppFeatures, TData, unknown>;
  label: string;
  triggerId: string;
  testIdPrefix: string;
}) {
  const meta = toolbarMeta(column.columnDef);
  const selected = (column.getFilterValue() as string[] | undefined) ?? [];
  const facets = column.getFacetedUniqueValues();
  const options = useMemo(
    () =>
      Array.from(facets.entries())
        .map(([raw, count]) => ({ value: String(raw), count: count as number }))
        .sort((a, b) => {
          const order = meta.facetOrder ?? [];
          const ia = order.indexOf(a.value);
          const ib = order.indexOf(b.value);
          if (ia !== ib) {
            if (ia === -1) return 1;
            if (ib === -1) return -1;
            return ia - ib;
          }
          return labelFor(meta, a.value).localeCompare(labelFor(meta, b.value));
        }),
    [facets, meta],
  );
  const toggle = (value: string) =>
    column.setFilterValue(
      selected.includes(value)
        ? selected.filter((v) => v !== value)
        : [...selected, value],
    );

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          id={triggerId}
          aria-label={label}
          data-testid={`${testIdPrefix}-facet-trigger-${column.id}`}
          className={TRIGGER_CLASS}
        >
          <span
            className={cn(
              'truncate',
              !selected.length && 'text-muted-foreground',
            )}
          >
            {selected.length === 0
              ? 'All'
              : selected.length <= 2
                ? selected.map((v) => labelFor(meta, v)).join(', ')
                : `${selected.length} selected`}
          </span>
          <ChevronDown className="size-4 shrink-0 opacity-50" aria-hidden />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-56 p-0"
        data-testid={`${testIdPrefix}-facet-panel-${column.id}`}
      >
        <Command>
          {options.length > 8 && <CommandInput placeholder={label} />}
          <CommandList>
            <CommandEmpty>No options.</CommandEmpty>
            <CommandGroup>
              {options.map((o) => {
                const checked = selected.includes(o.value);
                return (
                  <CommandItem
                    key={o.value}
                    value={labelFor(meta, o.value)}
                    onSelect={() => toggle(o.value)}
                    aria-checked={checked}
                    data-testid={`${testIdPrefix}-facet-option-${column.id}-${facetSlug(o.value)}`}
                  >
                    <CheckMark checked={checked} />
                    <span className="truncate">{labelFor(meta, o.value)}</span>
                    <span className="ml-auto text-xs tabular-nums text-muted-foreground">
                      {o.count}
                    </span>
                  </CommandItem>
                );
              })}
            </CommandGroup>
            {selected.length > 0 && (
              <>
                <CommandSeparator />
                <CommandGroup>
                  <CommandItem
                    onSelect={() => column.setFilterValue(undefined)}
                    className="justify-center"
                    data-testid={`${testIdPrefix}-facet-clear-${column.id}`}
                  >
                    Clear {label.toLowerCase()} filter
                  </CommandItem>
                </CommandGroup>
              </>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

export function DataTableColumnsMenu<TData extends RowData>({
  columns,
  triggerId,
  testIdPrefix,
}: {
  columns: Column<AppFeatures, TData, unknown>[];
  triggerId: string;
  testIdPrefix: string;
}) {
  const hidden = columns.filter((c) => !c.getIsVisible()).length;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          id={triggerId}
          aria-label="Columns"
          data-testid={`${testIdPrefix}-columns-trigger`}
          className={TRIGGER_CLASS}
        >
          <span className="flex items-center gap-2 truncate">
            <Columns3 className="size-4 shrink-0" aria-hidden />
            {hidden === 0 ? 'All shown' : `${hidden} hidden`}
          </span>
          <ChevronDown className="size-4 opacity-50" aria-hidden />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-56 p-0">
        <Command>
          <CommandList>
            <CommandGroup>
              {columns.map((c) => (
                <CommandItem
                  key={c.id}
                  value={toolbarMeta(c.columnDef).columnLabel}
                  onSelect={() => c.toggleVisibility()}
                  aria-checked={c.getIsVisible()}
                  data-testid={`${testIdPrefix}-columns-option-${c.id}`}
                >
                  <CheckMark checked={c.getIsVisible()} />
                  {toolbarMeta(c.columnDef).columnLabel}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

/**
 * Filter bar built from the table's own column defs: a column joins with
 * `meta.filterLabel` (faceted filter) or `meta.columnLabel` (Columns menu). Renders
 * nothing when no column opts in and there is no search.
 */
export function DataTableToolbar<TData extends RowData>({
  table,
  search,
  globalSearch,
  testIdPrefix = 'table',
}: {
  table: ReactTable<AppFeatures, TData>;
  search?: DataTableSearch;
  globalSearch?: DataTableGlobalSearch;
  testIdPrefix?: string;
}) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const isMobile = useMediaQuery(TABLE_TOOLBAR_MOBILE_QUERY);
  const baseId = useId();

  const leaf = table.getAllLeafColumns();
  const filterCols = leaf.filter((c) => toolbarMeta(c.columnDef).filterLabel);
  const visibilityCols = leaf.filter(
    (c) => toolbarMeta(c.columnDef).columnLabel,
  );
  if (
    filterCols.length === 0 &&
    visibilityCols.length === 0 &&
    !search &&
    !globalSearch
  ) {
    return null;
  }

  const filters = table.state.columnFilters ?? [];
  const globalFilter = (table.state.globalFilter as string | undefined) ?? '';
  const selectedCount = filters.reduce(
    (n, f) => n + (Array.isArray(f.value) ? f.value.length : 0),
    0,
  );
  const active = filters.length > 0 || globalFilter !== '';

  const searchField = search ? (
    <ToolbarField
      htmlFor={`${baseId}-search`}
      label={search.label ?? 'Search'}
      className="min-w-48 flex-1 sm:w-64 sm:flex-none"
    >
      <Input
        id={`${baseId}-search`}
        data-testid={`${testIdPrefix}-search`}
        value={search.value}
        onChange={(e) => search.onChange(e.target.value)}
        placeholder={search.placeholder}
        className="min-h-11 sm:min-h-8"
      />
    </ToolbarField>
  ) : globalSearch ? (
    <ToolbarField
      htmlFor={`${baseId}-search`}
      label={globalSearch.label ?? 'Search'}
      className="min-w-48 flex-1 sm:w-64 sm:flex-none"
    >
      <Input
        id={`${baseId}-search`}
        data-testid={`${testIdPrefix}-search`}
        value={globalFilter}
        onChange={(e) => table.setGlobalFilter(e.target.value)}
        placeholder={globalSearch.placeholder}
        className="min-h-11 sm:min-h-8"
      />
    </ToolbarField>
  ) : null;

  const controls = (
    <>
      {filterCols.map((c) => {
        const id = `${baseId}-facet-${c.id}`;
        const label = toolbarMeta(c.columnDef).filterLabel!;
        return (
          <ToolbarField key={c.id} htmlFor={id} label={label}>
            <DataTableFacetedFilter
              column={c}
              label={label}
              triggerId={id}
              testIdPrefix={testIdPrefix}
            />
          </ToolbarField>
        );
      })}
      {visibilityCols.length > 0 && (
        <ToolbarField htmlFor={`${baseId}-columns`} label="Columns">
          <DataTableColumnsMenu
            columns={visibilityCols}
            triggerId={`${baseId}-columns`}
            testIdPrefix={testIdPrefix}
          />
        </ToolbarField>
      )}
      {active && (
        <SecondaryButton
          size="sm"
          className="min-h-11 sm:min-h-8"
          data-testid={`${testIdPrefix}-filters-reset`}
          onClick={() => {
            table.resetColumnFilters();
            table.setGlobalFilter('');
          }}
        >
          Reset
        </SecondaryButton>
      )}
    </>
  );

  const hasControls = filterCols.length > 0 || visibilityCols.length > 0;

  return (
    <div
      data-testid={`${testIdPrefix}-toolbar`}
      className="flex flex-wrap items-end gap-2"
    >
      {searchField}
      {hasControls && isMobile && (
        <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
          <SheetTrigger asChild>
            <Button
              variant="outline"
              data-testid={`${testIdPrefix}-filters-sheet-trigger`}
              className="min-h-11 shrink-0"
            >
              <SlidersHorizontal className="size-4" aria-hidden />
              Filters
              {selectedCount > 0 && (
                <Badge variant="secondary" className="tabular-nums">
                  {selectedCount}
                </Badge>
              )}
            </Button>
          </SheetTrigger>
          <SheetContent
            side="right"
            data-testid={`${testIdPrefix}-filters-sheet`}
            className="w-full max-w-sm bg-card"
          >
            <SheetHeader>
              <SheetTitle>Filters</SheetTitle>
              <SheetDescription>
                Changes apply to the table immediately.
              </SheetDescription>
            </SheetHeader>
            <div className="mt-4 flex flex-col gap-4">{controls}</div>
          </SheetContent>
        </Sheet>
      )}
      {!isMobile && controls}
      {filters.length > 0 && (
        <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
          {filters.flatMap((f) => {
            const column = table.getColumn(f.id);
            const meta = toolbarMeta(column?.columnDef ?? {});
            const values = Array.isArray(f.value) ? (f.value as string[]) : [];
            return values.map((v) => (
              <Badge
                key={`${f.id}-${v}`}
                variant="outline"
                className="gap-1 border-primary/60 py-0.5"
                data-testid={`${testIdPrefix}-filter-chip-${f.id}-${facetSlug(v)}`}
              >
                {meta.filterLabel ?? f.id}: {labelFor(meta, v)}
                <RemoveIconButton
                  label={`Remove ${labelFor(meta, v)} filter`}
                  data-testid={`${testIdPrefix}-filter-chip-remove-${f.id}-${facetSlug(v)}`}
                  onClick={() =>
                    column?.setFilterValue(values.filter((x) => x !== v))
                  }
                />
              </Badge>
            ));
          })}
        </div>
      )}
    </div>
  );
}
