import * as TabsPrimitive from '@radix-ui/react-tabs';
import { Search } from 'lucide-react';
import * as React from 'react';
import {
  FormTabsList,
  InvalidDot,
  type FormTabItem,
} from '~/components/patterns/FormTabsList';
import { Button } from '~/components/ui/button';
import { FormDialog, type FormDialogProps } from '~/components/ui/dialogs';
import { Input } from '~/components/ui/input';
import { Kbd } from '~/components/ui/kbd';
import { ScrollArea } from '~/components/ui/scroll-area';
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
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
  key: string;
  section: V;
  label: string;
  el: HTMLElement;
}

const SEARCHABLE = 'label, h3, h4';
const FOCUSABLE =
  'input:not([type=hidden]), select, textarea, button, [tabindex]:not([tabindex="-1"])';
const HIGHLIGHT_MS = 1600;

function terms(query: string): string[] {
  return query.toLowerCase().split(/\s+/).filter(Boolean);
}

function matches(text: string, q: string[]): boolean {
  const t = text.toLowerCase();
  return q.every((term) => t.includes(term));
}

function isTypingTarget(t: HTMLElement): boolean {
  return (
    t.isContentEditable ||
    !!t.closest(
      'input, textarea, select, [role="combobox"], [role="listbox"], [role="menu"]',
    )
  );
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
  const isLoading = loading != null && loading !== false;
  const first = sections[0].value;
  const [active, setActive] = React.useState<V>(first);
  const [visited, setVisited] = React.useState<Set<V>>(() => new Set([first]));
  const [query, setQuery] = React.useState('');
  const [hits, setHits] = React.useState<SearchHit<V>[]>([]);
  const [domVersion, setDomVersion] = React.useState(0);
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
  const rafRef = React.useRef(0);
  const highlightRef = React.useRef<{ el: HTMLElement; timer: number } | null>(
    null,
  );
  const statusId = React.useId();

  const selectSection = React.useCallback((value: V) => {
    setActive(value);
    setVisited((prev) => (prev.has(value) ? prev : new Set(prev).add(value)));
  }, []);
  React.useImperativeHandle(sectionRef, () => ({ selectSection }), [
    selectSection,
  ]);

  const q = React.useMemo(() => terms(query), [query]);
  const searching = q.length > 0;
  const sectionKey = sections.map((s) => s.value).join('|');

  // Fields come and go with form state (conditional sections, lazy data).
  React.useEffect(() => {
    if (!searching) return;
    const observer = new MutationObserver(() => setDomVersion((v) => v + 1));
    for (const panel of panels.current.values()) {
      observer.observe(panel, {
        childList: true,
        subtree: true,
        characterData: true,
      });
    }
    return () => observer.disconnect();
  }, [searching, visited, sectionKey]);

  React.useLayoutEffect(() => {
    if (!searching) {
      setHits([]);
      return;
    }
    const found: SearchHit<V>[] = [];
    for (const s of sections) {
      const panel = panels.current.get(s.value);
      if (!panel) continue;
      panel.querySelectorAll<HTMLElement>(SEARCHABLE).forEach((el, i) => {
        const label = el.textContent?.trim();
        if (!label || !matches(label, q)) return;
        found.push({ key: `${s.value}:${i}`, section: s.value, label, el });
      });
    }
    setHits(found);
    // `sections` is a fresh array each render; sectionKey tracks its identity.
  }, [q, visited, sectionKey, domVersion]);

  const matchedSections = new Set<V>(hits.map((h) => h.section));
  for (const s of sections) {
    if (matches([s.label, ...(s.keywords ?? [])].join(' '), q)) {
      matchedSections.add(s.value);
    }
  }
  // The active category stays listed so focus never lands on a missing tab.
  const visible = searching
    ? sections.filter((s) => matchedSections.has(s.value) || s.value === active)
    : sections;
  const noMatches = searching && matchedSections.size === 0;

  const clearHighlight = React.useCallback(() => {
    const h = highlightRef.current;
    if (!h) return;
    window.clearTimeout(h.timer);
    delete h.el.dataset.searchHit;
    highlightRef.current = null;
  }, []);

  React.useEffect(() => {
    if (open) return;
    cancelAnimationFrame(rafRef.current);
    clearHighlight();
  }, [open, clearHighlight]);
  React.useEffect(
    () => () => {
      cancelAnimationFrame(rafRef.current);
      clearHighlight();
    },
    [clearHighlight],
  );

  const jumpTo = React.useCallback(
    (hit: SearchHit<V>) => {
      if (!hit.el.isConnected) return;
      selectSection(hit.section);
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        const label = hit.el instanceof HTMLLabelElement ? hit.el : null;
        const target = label ? (label.parentElement ?? label) : hit.el;
        target.scrollIntoView({ block: 'center', behavior: 'smooth' });

        const focusable =
          label?.control ??
          (label?.htmlFor ? document.getElementById(label.htmlFor) : null) ??
          (label ? target.querySelector<HTMLElement>(FOCUSABLE) : null);
        if (focusable) {
          focusable.focus({ preventScroll: true });
        } else {
          target.tabIndex = -1;
          target.focus({ preventScroll: true });
        }

        clearHighlight();
        target.dataset.searchHit = '';
        highlightRef.current = {
          el: target,
          timer: window.setTimeout(clearHighlight, HIGHLIGHT_MS),
        };
      });
    },
    [selectSection, clearHighlight],
  );

  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== '/' || e.defaultPrevented) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      const dialog = searchRef.current?.closest('[role="dialog"]');
      if (!t || !dialog?.contains(t) || isTypingTarget(t)) return;
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
    const firstMatch = visible.find((s) => matchedSections.has(s.value));
    if (hits[0]) jumpTo(hits[0]);
    else if (firstMatch) selectSection(firstMatch.value);
  };

  const sectionLabel = (value: V) =>
    sections.find((s) => s.value === value)?.label;

  const status = !searching
    ? ''
    : noMatches
      ? `No settings match “${query.trim()}”`
      : `${hits.length} matching ${hits.length === 1 ? 'setting' : 'settings'}`;

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
        aria-describedby={statusId}
        aria-keyshortcuts="/"
        data-escape-clears=""
        data-testid={`${testIdPrefix}-search`}
        className="h-9 pr-8 pl-8"
      />
      {!query && (
        <Kbd className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2">
          /
        </Kbd>
      )}
      <p id={statusId} role="status" className="sr-only">
        {status}
      </p>
    </div>
  );

  const emptyState = noMatches && (
    <p
      className="px-2 py-3 text-sm text-muted-foreground"
      data-testid={`${testIdPrefix}-search-empty`}
    >
      {status}
    </p>
  );

  const hitList = hits.length > 0 && (
    <ul aria-label="Matching settings" className="flex flex-col gap-0.5">
      {hits.map((hit) => (
        <li key={hit.key}>
          <Button
            type="button"
            variant="ghost"
            onClick={() => jumpTo(hit)}
            data-testid={`${testIdPrefix}-search-hit`}
            className={cn(
              'h-auto w-full justify-start gap-1.5 px-2 py-1.5 text-left font-normal',
              isMobile ? 'min-h-11' : 'min-h-8',
            )}
          >
            <span className="min-w-0 truncate">{hit.label}</span>
            <span className="shrink-0 text-xs text-muted-foreground">
              {sectionLabel(hit.section)}
            </span>
          </Button>
        </li>
      ))}
    </ul>
  );

  const desktopNav = (
    <SidebarProvider
      keyboardShortcut={false}
      className="min-h-0 w-auto flex-none"
      style={{ '--sidebar-width': '15rem' } as React.CSSProperties}
    >
      <Sidebar
        collapsible="none"
        className="h-full rounded-lg border border-sidebar-border"
        data-testid={`${testIdPrefix}-sidebar`}
      >
        <SidebarHeader>{search}</SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            {searching && <SidebarGroupLabel>Categories</SidebarGroupLabel>}
            <SidebarGroupContent>
              {emptyState}
              <TabsPrimitive.List asChild>
                <SidebarMenu>
                  {visible.map((s) => {
                    const Icon = s.icon;
                    return (
                      <SidebarMenuItem key={s.value} role="none">
                        <TabsPrimitive.Trigger value={s.value} asChild>
                          <SidebarMenuButton
                            isActive={active === s.value}
                            data-testid={`${testIdPrefix}-tab-${s.value}`}
                            data-invalid={s.invalid || undefined}
                            className={cn(
                              'cursor-pointer',
                              searching &&
                                !matchedSections.has(s.value) &&
                                'opacity-60',
                            )}
                          >
                            {Icon && <Icon />}
                            <span className="min-w-0 flex-1 truncate">
                              {s.label}
                            </span>
                            {s.invalid && <InvalidDot />}
                          </SidebarMenuButton>
                        </TabsPrimitive.Trigger>
                      </SidebarMenuItem>
                    );
                  })}
                </SidebarMenu>
              </TabsPrimitive.List>
            </SidebarGroupContent>
          </SidebarGroup>
          {hitList && (
            <SidebarGroup>
              <SidebarGroupLabel>Matching settings</SidebarGroupLabel>
              <SidebarGroupContent>{hitList}</SidebarGroupContent>
            </SidebarGroup>
          )}
        </SidebarContent>
      </Sidebar>
    </SidebarProvider>
  );

  const mobileNav = (
    <div className="flex flex-col gap-3">
      {search}
      {emptyState || (
        <FormTabsList tabs={visible} testIdPrefix={testIdPrefix} />
      )}
      {hitList && (
        <ScrollArea
          className="rounded-md border border-border"
          viewportProps={{ className: 'max-h-40 p-1' }}
        >
          {hitList}
        </ScrollArea>
      )}
    </div>
  );

  // `body` keeps its tree position across layouts so crossing the breakpoint
  // swaps only the navigation, never remounting the form.
  const frame = (body: React.ReactNode) => (
    <Tabs
      value={active}
      onValueChange={(v) => selectSection(v as V)}
      orientation={isMobile ? 'horizontal' : 'vertical'}
      className={cn(
        'min-h-0 flex-1',
        isMobile ? 'flex-col gap-3' : 'flex-row gap-6',
      )}
    >
      {isMobile ? mobileNav : desktopNav}
      {body}
    </Tabs>
  );

  return (
    <FormDialog
      open={open}
      size="screen"
      {...dialogProps}
      frame={isLoading ? undefined : frame}
      scrollClassName={
        isLoading
          ? undefined
          : isMobile
            ? 'min-h-0 flex-1 overflow-hidden -mx-6 px-6'
            : 'min-h-0 flex-1 overflow-hidden -mr-6 pr-6'
      }
    >
      {isLoading
        ? loading
        : sections.map((s) => (
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
                '[&_[data-search-hit]]:rounded-md [&_[data-search-hit]]:ring-2 [&_[data-search-hit]]:ring-ring [&_[data-search-hit]]:ring-offset-2 [&_[data-search-hit]]:ring-offset-background',
              )}
            >
              {s.content}
            </TabsContent>
          ))}
    </FormDialog>
  );
}
