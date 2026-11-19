import * as TabsPrimitive from '@radix-ui/react-tabs';
import { Search } from 'lucide-react';
import * as React from 'react';
import {
  FormTabsList,
  InvalidDot,
  type FormTabItem,
} from '~/components/patterns/FormTabsList';
import { FormDialog, type FormDialogProps } from '~/components/ui/dialogs';
import { Input } from '~/components/ui/input';
import { Kbd } from '~/components/ui/kbd';
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarProvider,
} from '~/components/ui/sidebar';
import { Tabs, TabsContent } from '~/components/ui/tabs';
import { useMediaQuery } from '~/hooks/useMediaQuery';
import { cn } from '~/lib/utils';

export interface SettingsSection<
  V extends string = string,
> extends FormTabItem {
  value: V;
  content: React.ReactNode;
  /** Extra search terms, for settings a search can't read from the page. */
  keywords?: string[];
  /** Mount on first visit, then stay mounted. */
  lazy?: boolean;
}

export interface SettingsDialogHandle<V extends string = string> {
  selectSection: (value: V) => void;
}

export interface SettingsDialogProps<V extends string = string> extends Omit<
  FormDialogProps,
  'children' | 'size' | 'frame' | 'scrollClassName'
> {
  sections: SettingsSection<V>[];
  /** Nav items get `${testIdPrefix}-tab-${value}`. */
  testIdPrefix: string;
  /** Rendered instead of the sections when set. */
  loading?: React.ReactNode;
  sectionRef?: React.Ref<SettingsDialogHandle<V>>;
  searchPlaceholder?: string;
}

interface SearchHit<V extends string> {
  section: V;
  label: string;
  el: HTMLElement;
}

const SEARCHABLE = 'label, h3, h4';
const HIGHLIGHT_MS = 1600;

function terms(query: string): string[] {
  return query.toLowerCase().split(/\s+/).filter(Boolean);
}

function matches(text: string, q: string[]): boolean {
  const t = text.toLowerCase();
  return q.every((term) => t.includes(term));
}

/**
 * Full-screen settings form: a searchable category sidebar (a tab strip on
 * phones) beside the active category's fields. Search matches category names,
 * keywords and the labels and headings rendered in each mounted category.
 */
export function SettingsDialog<V extends string>({
  open,
  sections,
  testIdPrefix,
  loading,
  sectionRef,
  searchPlaceholder = 'Search settings',
  ...dialogProps
}: SettingsDialogProps<V>) {
  const isMobile = useMediaQuery('(max-width: 767px)');
  const first = sections[0].value;
  const [active, setActive] = React.useState<V>(first);
  const [visited, setVisited] = React.useState<Set<V>>(() => new Set([first]));
  const [query, setQuery] = React.useState('');
  const [hits, setHits] = React.useState<SearchHit<V>[]>([]);
  const [wasOpen, setWasOpen] = React.useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setActive(first);
      setVisited(new Set([first]));
      setQuery('');
    }
  }

  const panels = React.useRef(new Map<V, HTMLElement>());
  const searchRef = React.useRef<HTMLInputElement>(null);

  const selectSection = React.useCallback((value: V) => {
    setActive(value);
    setVisited((prev) => (prev.has(value) ? prev : new Set(prev).add(value)));
  }, []);
  React.useImperativeHandle(sectionRef, () => ({ selectSection }), [
    selectSection,
  ]);

  const q = React.useMemo(() => terms(query), [query]);
  const sectionKey = sections.map((s) => s.value).join('|');
  React.useLayoutEffect(() => {
    if (q.length === 0) {
      setHits([]);
      return;
    }
    const found: SearchHit<V>[] = [];
    for (const [section, panel] of panels.current) {
      const seen = new Set<string>();
      panel.querySelectorAll<HTMLElement>(SEARCHABLE).forEach((el) => {
        const label = el.textContent?.trim();
        if (!label || seen.has(label) || !matches(label, q)) return;
        seen.add(label);
        found.push({ section, label, el });
      });
    }
    setHits(found);
  }, [q, visited, sectionKey]);

  const hitsBySection = React.useMemo(() => {
    const by = new Map<V, SearchHit<V>[]>();
    for (const hit of hits) {
      by.set(hit.section, [...(by.get(hit.section) ?? []), hit]);
    }
    return by;
  }, [hits]);

  const visible =
    q.length === 0
      ? sections
      : sections.filter(
          (s) =>
            hitsBySection.has(s.value) ||
            matches([s.label, ...(s.keywords ?? [])].join(' '), q),
        );

  const jumpTo = React.useCallback(
    (hit: SearchHit<V>) => {
      selectSection(hit.section);
      requestAnimationFrame(() => {
        const target = hit.el.parentElement ?? hit.el;
        target.scrollIntoView({ block: 'center', behavior: 'smooth' });
        const forId =
          hit.el instanceof HTMLLabelElement ? hit.el.htmlFor : undefined;
        const control = forId ? document.getElementById(forId) : null;
        control?.focus({ preventScroll: true });
        target.dataset.searchHit = '';
        window.setTimeout(() => delete target.dataset.searchHit, HIGHLIGHT_MS);
      });
    },
    [selectSection],
  );

  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (t.isContentEditable ||
          ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName))
      ) {
        return;
      }
      e.preventDefault();
      searchRef.current?.focus();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  const onSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape' && query) {
      setQuery('');
      return;
    }
    if (e.key !== 'Enter') return;
    // Keep FormDialog's Enter-to-submit away from the search box.
    e.preventDefault();
    e.stopPropagation();
    if (hits[0]) jumpTo(hits[0]);
    else if (visible[0]) selectSection(visible[0].value);
  };

  const search = (
    <div className="relative">
      <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        ref={searchRef}
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={onSearchKeyDown}
        placeholder={searchPlaceholder}
        aria-label={searchPlaceholder}
        data-escape-clears=""
        data-testid={`${testIdPrefix}-search`}
        className="h-9 pr-8 pl-8"
      />
      {!query && (
        <Kbd className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2">
          /
        </Kbd>
      )}
    </div>
  );

  const noMatches = q.length > 0 && visible.length === 0 && (
    <p
      className="px-2 py-3 text-sm text-muted-foreground"
      data-testid={`${testIdPrefix}-search-empty`}
    >
      No settings match “{query.trim()}”
    </p>
  );

  const hitButton = (hit: SearchHit<V>, withSection: boolean) => (
    <button
      type="button"
      onClick={() => jumpTo(hit)}
      data-testid={`${testIdPrefix}-search-hit`}
      className={cn(
        'w-full truncate text-left',
        withSection && 'min-h-11 px-3 py-2 hover:bg-accent',
      )}
    >
      {hit.label}
      {withSection && (
        <span className="text-muted-foreground">
          {' · '}
          {sections.find((s) => s.value === hit.section)?.label}
        </span>
      )}
    </button>
  );

  const frame = (body: React.ReactNode) => (
    <Tabs
      value={active}
      onValueChange={(v) => selectSection(v as V)}
      orientation={isMobile ? 'horizontal' : 'vertical'}
      className="min-h-0 flex-1 gap-3"
    >
      {isMobile ? (
        <>
          {search}
          {noMatches || (
            <FormTabsList tabs={visible} testIdPrefix={testIdPrefix} />
          )}
          {hits.length > 0 && (
            <ul className="max-h-40 overflow-y-auto rounded-md border border-border text-sm">
              {hits.map((hit) => (
                <li
                  key={`${hit.section}:${hit.label}`}
                  className="border-b border-border last:border-b-0"
                >
                  {hitButton(hit, true)}
                </li>
              ))}
            </ul>
          )}
          {body}
        </>
      ) : (
        <SidebarProvider
          className="min-h-0 flex-1 items-stretch gap-6"
          style={{ '--sidebar-width': '15rem' } as React.CSSProperties}
        >
          <Sidebar
            collapsible="none"
            className="rounded-lg border border-sidebar-border"
            data-testid={`${testIdPrefix}-sidebar`}
          >
            <SidebarHeader>{search}</SidebarHeader>
            <SidebarContent>
              <SidebarGroup>
                <SidebarGroupContent>
                  {noMatches}
                  <TabsPrimitive.List asChild>
                    <SidebarMenu>
                      {visible.map((s) => {
                        const sectionHits = hitsBySection.get(s.value) ?? [];
                        const Icon = s.icon;
                        return (
                          <SidebarMenuItem key={s.value} role="none">
                            <TabsPrimitive.Trigger value={s.value} asChild>
                              <SidebarMenuButton
                                isActive={active === s.value}
                                data-testid={`${testIdPrefix}-tab-${s.value}`}
                                data-invalid={s.invalid || undefined}
                                className="cursor-pointer"
                              >
                                {Icon && <Icon />}
                                <span className="flex-1">{s.label}</span>
                                {s.invalid && <InvalidDot />}
                              </SidebarMenuButton>
                            </TabsPrimitive.Trigger>
                            {sectionHits.length > 0 && (
                              <SidebarMenuSub role="none">
                                {sectionHits.map((hit) => (
                                  <SidebarMenuSubItem
                                    key={hit.label}
                                    role="none"
                                  >
                                    <SidebarMenuSubButton asChild>
                                      {hitButton(hit, false)}
                                    </SidebarMenuSubButton>
                                  </SidebarMenuSubItem>
                                ))}
                              </SidebarMenuSub>
                            )}
                          </SidebarMenuItem>
                        );
                      })}
                    </SidebarMenu>
                  </TabsPrimitive.List>
                </SidebarGroupContent>
              </SidebarGroup>
            </SidebarContent>
          </Sidebar>
          {body}
        </SidebarProvider>
      )}
    </Tabs>
  );

  return (
    <FormDialog
      open={open}
      size="screen"
      {...dialogProps}
      frame={loading ? undefined : frame}
      scrollClassName={
        loading
          ? undefined
          : isMobile
            ? 'min-h-0 flex-1 overflow-hidden -mx-6 px-6'
            : 'min-h-0 flex-1 overflow-hidden -mr-6 pr-6'
      }
    >
      {loading ??
        sections.map((s) => (
          <TabsContent
            key={s.value}
            value={s.value}
            ref={(el: HTMLDivElement | null) => {
              if (el) panels.current.set(s.value, el);
              else panels.current.delete(s.value);
            }}
            forceMount={!s.lazy || visited.has(s.value) ? true : undefined}
            // Radix leaves force-mounted panels visible; hide inactive ones.
            hidden={active !== s.value}
            className={cn(
              'mx-auto flex w-full max-w-4xl flex-col gap-4',
              '[&_[data-search-hit]]:rounded-md [&_[data-search-hit]]:ring-2 [&_[data-search-hit]]:ring-ring [&_[data-search-hit]]:ring-offset-4 [&_[data-search-hit]]:ring-offset-background',
            )}
          >
            {s.content}
          </TabsContent>
        ))}
    </FormDialog>
  );
}
