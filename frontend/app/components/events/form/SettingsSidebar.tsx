import * as TabsPrimitive from '@radix-ui/react-tabs';
import { CircleAlert, SearchIcon } from 'lucide-react';
import * as React from 'react';
import {
  BrandSelect,
  BrandSelectContent,
  BrandSelectItem,
  BrandSelectTrigger,
  SelectValue,
} from '~/components/ui/brand-select';
import { brandSecondary } from '~/components/ui/buttons';
import { RemoveIconButton } from '~/components/ui/buttons/icons';
import { Input } from '~/components/ui/input';
import { Kbd } from '~/components/ui/kbd';
import { cn } from '~/lib/utils';
import type { SettingsIndexEntry, SettingsSearchGroup } from './settingsSearch';
import type { EventFormTabValue } from './tabs';

export interface SidebarSection {
  value: EventFormTabValue;
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  hasError: boolean;
}

interface SettingsSidebarProps {
  sections: SidebarSection[];
  active: EventFormTabValue;
  onSelect: (value: EventFormTabValue) => void;
  query: string;
  onQueryChange: (query: string) => void;
  groups: SettingsSearchGroup[];
  onPick: (entry: SettingsIndexEntry) => void;
  /** Section items get `${testIdPrefix}-tab-${value}`. */
  testIdPrefix: string;
  searchRef: React.Ref<HTMLInputElement>;
}

function ErrorMarker({ testId }: { testId: string }) {
  return (
    <>
      <CircleAlert
        aria-hidden
        className="ml-auto size-4 shrink-0 text-destructive"
        data-testid={testId}
      />
      <span className="sr-only">has errors</span>
    </>
  );
}

/**
 * Section navigation and settings search for the event form dialogs: a vertical
 * tab list from md up, a section picker below md, and a search that lists matching
 * fields grouped by section in place of the tab list while it has a query.
 */
export function SettingsSidebar({
  sections,
  active,
  onSelect,
  query,
  onQueryChange,
  groups,
  onPick,
  testIdPrefix: p,
  searchRef,
}: SettingsSidebarProps) {
  const listId = React.useId();
  const searching = query.trim() !== '';
  const results = React.useMemo(
    () => groups.flatMap((g) => g.entries),
    [groups],
  );
  const [cursor, setCursor] = React.useState(0);
  const [lastQuery, setLastQuery] = React.useState(query);
  if (query !== lastQuery) {
    setLastQuery(query);
    setCursor(0);
  }
  const optionId = (field: string) => `${listId}-${field}`;
  const current = results[cursor];
  const meta = new Map(sections.map((s) => [s.value, s]));
  const ActiveIcon = meta.get(active)?.icon;

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!results.length) return;
    const last = results.length - 1;
    const moves: Record<string, number> = {
      ArrowDown: cursor === last ? 0 : cursor + 1,
      ArrowUp: cursor === 0 ? last : cursor - 1,
      Home: 0,
      End: last,
    };
    if (e.key in moves) {
      e.preventDefault();
      setCursor(moves[e.key]);
      document
        .getElementById(optionId(results[moves[e.key]].field))
        ?.scrollIntoView?.({ block: 'nearest' });
    } else if (e.key === 'Enter' && current) {
      e.preventDefault();
      e.stopPropagation();
      onPick(current);
    }
  };

  return (
    <nav
      aria-label="Settings sections"
      className="sticky top-0 z-10 flex flex-col gap-2 bg-background pb-2 md:w-60 md:shrink-0 md:self-start md:bg-transparent md:pb-0"
      data-testid={`${p}-settings-sidebar`}
    >
      <div className="relative">
        <SearchIcon
          aria-hidden
          className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          ref={searchRef}
          type="search"
          role="combobox"
          aria-label="Search settings"
          aria-expanded={searching}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={
            searching && current ? optionId(current.field) : undefined
          }
          autoComplete="off"
          placeholder="Search settings"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={onKeyDown}
          className="min-h-11 pr-12 pl-9 [&::-webkit-search-cancel-button]:hidden"
          data-testid={`${p}-settings-search`}
        />
        <div className="absolute top-1/2 right-1 flex -translate-y-1/2 items-center">
          {searching ? (
            <RemoveIconButton
              label="Clear search"
              className="mr-0 size-11 md:size-8"
              onClick={() => onQueryChange('')}
              data-testid={`${p}-settings-search-clear`}
            />
          ) : (
            <Kbd aria-hidden className="mr-2 hidden md:inline-flex">
              /
            </Kbd>
          )}
        </div>
      </div>

      {searching && (
        <div
          id={listId}
          role="listbox"
          aria-label="Matching settings"
          className="flex max-h-[50svh] flex-col gap-1 overflow-y-auto rounded-md border border-border/50 p-1 md:max-h-[65vh]"
          data-testid={`${p}-search-results`}
        >
          {results.length === 0 && (
            <p
              className="px-3 py-4 text-sm text-muted-foreground"
              data-testid={`${p}-search-empty`}
            >
              No settings match “{query.trim()}”
            </p>
          )}
          {groups.map(({ section, entries }) => {
            const s = meta.get(section);
            const Icon = s?.icon;
            const empty = entries.length === 0;
            return (
              <div
                key={section}
                role="group"
                aria-label={s?.label}
                data-empty={empty ? '' : undefined}
                className={cn('flex flex-col', empty && 'opacity-50')}
                data-testid={`${p}-search-group-${section}`}
              >
                <div className="flex items-center gap-2 px-2 py-1.5 text-xs font-medium text-muted-foreground">
                  {Icon && <Icon className="size-3.5" />}
                  <span>{s?.label}</span>
                  <span className="ml-auto tabular-nums">
                    {empty ? 'No matches' : entries.length}
                  </span>
                </div>
                {entries.map((entry) => {
                  const selected = entry === current;
                  return (
                    <div
                      key={entry.field}
                      id={optionId(entry.field)}
                      role="option"
                      aria-selected={selected}
                      // Keep focus in the search box; the pick moves it to the field.
                      onMouseDown={(e) => e.preventDefault()}
                      onMouseEnter={() => setCursor(results.indexOf(entry))}
                      onClick={() => onPick(entry)}
                      className={cn(
                        'flex min-h-11 cursor-pointer flex-col justify-center rounded-md px-3 py-1.5 text-sm',
                        selected
                          ? brandSecondary
                          : 'text-foreground hover:bg-primary/10',
                      )}
                      data-testid={`${p}-search-result-${entry.field}`}
                    >
                      <span className="font-medium">{entry.label}</span>
                      {entry.description && (
                        <span
                          className={cn(
                            'line-clamp-1 text-xs',
                            !selected && 'text-muted-foreground',
                          )}
                        >
                          {entry.description}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      )}

      {!searching && (
        <>
          <BrandSelect
            value={active}
            onValueChange={(v) => onSelect(v as EventFormTabValue)}
          >
            <BrandSelectTrigger
              aria-label="Settings section"
              className="min-h-11 w-full md:hidden"
              data-testid={`${p}-section-picker`}
            >
              <SelectValue>
                <span className="flex w-full items-center gap-2">
                  {ActiveIcon && <ActiveIcon className="size-4" />}
                  {meta.get(active)?.label}
                  {sections.some((s) => s.hasError) && (
                    <ErrorMarker testId={`${p}-section-picker-error`} />
                  )}
                </span>
              </SelectValue>
            </BrandSelectTrigger>
            <BrandSelectContent>
              {sections.map(({ value, label, icon: Icon, hasError }) => (
                <BrandSelectItem
                  key={value}
                  value={value}
                  className="min-h-11"
                  data-testid={`${p}-section-option-${value}`}
                >
                  <span className="flex w-full items-center gap-2">
                    {Icon && <Icon className="size-4" />}
                    {label}
                    {hasError && (
                      <ErrorMarker
                        testId={`${p}-section-option-${value}-error`}
                      />
                    )}
                  </span>
                </BrandSelectItem>
              ))}
            </BrandSelectContent>
          </BrandSelect>

          <TabsPrimitive.List
            aria-label="Settings sections"
            className="hidden flex-col gap-1 md:flex"
          >
            {sections.map(({ value, label, icon: Icon, hasError }) => (
              <TabsPrimitive.Trigger
                key={value}
                value={value}
                className={cn(
                  'flex min-h-11 w-full cursor-pointer items-center gap-3 rounded-md px-3 text-left text-sm font-medium outline-none transition-colors',
                  'focus-visible:ring-2 focus-visible:ring-ring',
                  value === active
                    ? brandSecondary
                    : 'text-muted-foreground hover:bg-primary/10 hover:text-foreground',
                )}
                data-testid={`${p}-tab-${value}`}
              >
                {Icon && <Icon className="size-4 shrink-0" />}
                <span>{label}</span>
                {hasError && <ErrorMarker testId={`${p}-tab-${value}-error`} />}
              </TabsPrimitive.Trigger>
            ))}
          </TabsPrimitive.List>
        </>
      )}
    </nav>
  );
}
