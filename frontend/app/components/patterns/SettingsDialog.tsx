import * as TabsPrimitive from '@radix-ui/react-tabs';
import { Search } from 'lucide-react';
import * as React from 'react';
import { useSearchParams } from 'react-router';
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

export interface SettingsFieldInfo {
  label: string;
  description?: string;
  /** Search terms that appear in neither the label nor the description. */
  keywords?: readonly string[];
}

export interface SettingsSection<
  V extends string = string,
> extends FormTabItem {
  value: V;
  content: React.ReactNode;
  /** Extra search terms, for settings a search can't read from the page. */
  keywords?: string[];
  /** Mount on first visit, then stay mounted. */
  lazy?: boolean;
  /**
   * Form fields this section renders, by field name. Search finds them before
   * a lazy section is visited and inside collapsed blocks that declare them
   * with `data-fields="a b"`; rendered rows are found by `data-field`.
   */
  fields?: Readonly<Record<string, SettingsFieldInfo>>;
}

export interface SettingsDialogHandle<V extends string = string> {
  selectSection: (value: V) => void;
  /** The section that renders `field` (or a collapsed block holding it), else its registered section. */
  sectionOfField: (field: string) => V | undefined;
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
  /** A rendered label/heading, or the collapsed block that holds `field`. */
  el?: HTMLElement;
  field?: string;
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

const attr = (value: string) => value.replace(/["\\]/g, '\\$&');
const fieldRow = (field: string) => `[data-field="${attr(field)}"]`;
const fieldBlock = (field: string) => `[data-fields~="${attr(field)}"]`;

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
interface SettingsLayoutOptions<V extends string> {
  /** Resets to the first section each time this turns true. */
  open: boolean;
  sections: SettingsSection<V>[];
  testIdPrefix: string;
  sectionRef?: React.Ref<SettingsDialogHandle<V>>;
  searchPlaceholder?: string;
  variant: 'dialog' | 'page';
  /** Requested section, e.g. from the URL; falls back to the first when unknown or hidden. */
  value?: string | null;
  onValueChange?: (value: V) => void;
}

/** Sidebar, search and section panels shared by SettingsDialog and SettingsPage. */
function useSettingsLayout<V extends string>({
  open,
  sections,
  testIdPrefix,
  sectionRef,
  searchPlaceholder = 'Search settings',
  variant,
  value,
  onValueChange,
}: SettingsLayoutOptions<V>) {
  const isMobile = useMediaQuery('(max-width: 767px)');
  const first = sections[0].value;
  const [localActive, setActive] = React.useState<V>(first);
  const requested = value === undefined ? localActive : value;
  const active = sections.find((s) => s.value === requested)?.value ?? first;
  const [visited, setVisited] = React.useState<Set<V>>(() => new Set([active]));
  if (!visited.has(active)) setVisited(new Set(visited).add(active));
  const [query, setQuery] = React.useState('');
  const [hits, setHits] = React.useState<SearchHit<V>[]>([]);
  const [cursor, setCursor] = React.useState(0);
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

  const panelEls = React.useRef(new Map<V, HTMLElement>());
  const searchRef = React.useRef<HTMLInputElement>(null);
  const rafRef = React.useRef(0);
  const highlightRef = React.useRef<{ el: HTMLElement; timer: number } | null>(
    null,
  );
  const statusId = React.useId();
  const hitIdPrefix = React.useId();

  const onValueChangeRef = React.useRef(onValueChange);
  onValueChangeRef.current = onValueChange;
  const selectSection = React.useCallback((next: V) => {
    setActive(next);
    setVisited((prev) => (prev.has(next) ? prev : new Set(prev).add(next)));
    onValueChangeRef.current?.(next);
  }, []);
  const sectionsRef = React.useRef(sections);
  sectionsRef.current = sections;
  const sectionOfField = React.useCallback((field: string): V | undefined => {
    for (const selector of [fieldRow(field), fieldBlock(field)]) {
      for (const [value, panel] of panelEls.current) {
        if (panel.querySelector(selector)) return value;
      }
    }
    return sectionsRef.current.find((s) => s.fields && field in s.fields)
      ?.value;
  }, []);
  React.useImperativeHandle(
    sectionRef,
    () => ({ selectSection, sectionOfField }),
    [selectSection, sectionOfField],
  );

  const q = React.useMemo(() => terms(query), [query]);
  const searching = q.length > 0;
  const sectionKey = sections.map((s) => s.value).join('|');

  // Fields come and go with form state (conditional sections, lazy data).
  React.useEffect(() => {
    if (!searching) return;
    const observer = new MutationObserver(() => setDomVersion((v) => v + 1));
    for (const panel of panelEls.current.values()) {
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
    const seen = new Set<string>();
    const registry = new Map<string, SettingsFieldInfo>();
    for (const s of sections) {
      for (const [field, info] of Object.entries(s.fields ?? {})) {
        if (!registry.has(field)) registry.set(field, info);
      }
    }
    // Every term must appear in the label, description or keywords.
    const add = (hit: SearchHit<V>, rest: string) => {
      if (matches(`${hit.label} ${rest}`, q)) found.push(hit);
    };

    // Rendered labels and headings, enriched by the registry when they sit in a field row.
    for (const s of sections) {
      const panel = panelEls.current.get(s.value);
      if (!panel) continue;
      panel.querySelectorAll<HTMLElement>(SEARCHABLE).forEach((el, i) => {
        const label = el.textContent?.trim();
        if (!label) return;
        // Only a row's first label names the field; option labels inside it stay plain hits.
        const row = el.closest<HTMLElement>('[data-field]');
        const field =
          row && row.querySelector('label') === el
            ? row.dataset.field
            : undefined;
        if (field) {
          if (seen.has(field)) return;
          seen.add(field);
        }
        const info = field ? registry.get(field) : undefined;
        const description = field
          ? row
              ?.querySelector('[id$="-form-item-description"]')
              ?.textContent?.trim()
          : undefined;
        add(
          { key: `${s.value}:${i}`, section: s.value, label, el, field },
          [
            description ?? info?.description ?? '',
            ...(info?.keywords ?? []),
          ].join(' '),
        );
      });
    }

    // Registered fields not rendered: inside a collapsed block, or in a lazy section not visited yet.
    for (const s of sections) {
      for (const [field, info] of Object.entries(s.fields ?? {})) {
        if (seen.has(field)) continue;
        let section: V | undefined;
        let el: HTMLElement | undefined;
        for (const [value, panel] of panelEls.current) {
          const block = panel.querySelector<HTMLElement>(fieldBlock(field));
          if (block) {
            section = value;
            el = block;
            break;
          }
        }
        if (!section && s.lazy && !visited.has(s.value)) section = s.value;
        if (!section) continue;
        seen.add(field);
        add(
          { key: `${section}:${field}`, section, label: info.label, el, field },
          [info.description ?? '', ...(info.keywords ?? [])].join(' '),
        );
      }
    }
    setHits(found);
    setCursor(0);
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

  const highlight = React.useCallback(
    (target: HTMLElement, focusable: HTMLElement | null) => {
      target.scrollIntoView({ block: 'center', behavior: 'smooth' });
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
    },
    [clearHighlight],
  );

  const revealLabel = React.useCallback(
    (label: HTMLElement) => {
      const asLabel = label instanceof HTMLLabelElement ? label : null;
      const row = label.closest<HTMLElement>('[data-field]');
      const target =
        row ?? (asLabel ? (asLabel.parentElement ?? asLabel) : label);
      const focusable =
        asLabel?.control ??
        (asLabel?.htmlFor ? document.getElementById(asLabel.htmlFor) : null) ??
        (asLabel || row ? target.querySelector<HTMLElement>(FOCUSABLE) : null);
      highlight(target, focusable);
    },
    [highlight],
  );

  const jumpTo = React.useCallback(
    (hit: SearchHit<V>) => {
      if (hit.el && !hit.el.isConnected) return;
      selectSection(hit.section);
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        const panel = panelEls.current.get(hit.section);
        const row = hit.field
          ? panel?.querySelector<HTMLElement>(fieldRow(hit.field))
          : null;
        if (row) {
          revealLabel(row.querySelector<HTMLElement>('label') ?? row);
          return;
        }
        const block =
          hit.el?.matches('[data-fields]') === true
            ? hit.el
            : hit.field
              ? panel?.querySelector<HTMLElement>(fieldBlock(hit.field))
              : null;
        if (block && hit.field) {
          const trigger = block.querySelector<HTMLElement>(
            '[aria-expanded="false"]:not(:disabled)',
          );
          if (!trigger) {
            highlight(block, block.querySelector<HTMLElement>(FOCUSABLE));
            return;
          }
          trigger.click();
          const field = hit.field;
          rafRef.current = requestAnimationFrame(() => {
            const opened = block.querySelector<HTMLElement>(fieldRow(field));
            if (opened)
              revealLabel(opened.querySelector<HTMLElement>('label') ?? opened);
            else highlight(block, trigger);
          });
          return;
        }
        if (hit.el) revealLabel(hit.el);
      });
    },
    [selectSection, highlight, revealLabel],
  );

  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.altKey) return;
      const t = e.target as HTMLElement | null;
      const root = searchRef.current?.closest(
        variant === 'dialog' ? '[role="dialog"]' : '[data-settings-root]',
      );
      // A page has no focus trap: a key pressed with nothing focused counts too.
      const inScope =
        !!t &&
        (!!root?.contains(t) || (variant === 'page' && t === document.body));
      if (!t || !inScope) return;
      const commandK =
        e.key.toLowerCase() === 'k' && (e.metaKey || e.ctrlKey) && !e.shiftKey;
      const slash =
        e.key === '/' && !e.metaKey && !e.ctrlKey && !isTypingTarget(t);
      if (!commandK && !slash) return;
      e.preventDefault();
      searchRef.current?.focus();
      searchRef.current?.select();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  const onSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape' && query) {
      setQuery('');
      return;
    }
    if (hits.length > 0) {
      const last = hits.length - 1;
      const next: Record<string, number> = {
        ArrowDown: cursor >= last ? 0 : cursor + 1,
        ArrowUp: cursor <= 0 ? last : cursor - 1,
        Home: 0,
        End: last,
      };
      if (e.key in next) {
        e.preventDefault();
        setCursor(next[e.key]);
        document
          .getElementById(`${hitIdPrefix}-${next[e.key]}`)
          ?.scrollIntoView({ block: 'nearest' });
        return;
      }
    }
    if (e.key !== 'Enter') return;
    // Keep FormDialog's Enter-to-submit away from the search box.
    e.preventDefault();
    e.stopPropagation();
    const firstMatch = visible.find((s) => matchedSections.has(s.value));
    const picked = hits[cursor] ?? hits[0];
    if (picked) jumpTo(picked);
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
        aria-keyshortcuts="/ Control+K Meta+K"
        aria-controls={hits.length > 0 ? `${hitIdPrefix}-list` : undefined}
        aria-activedescendant={
          hits.length > 0 ? `${hitIdPrefix}-${cursor}` : undefined
        }
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
    <ul
      id={`${hitIdPrefix}-list`}
      role="listbox"
      aria-label="Matching settings"
      className="flex flex-col gap-0.5"
    >
      {hits.map((hit, i) => (
        <li key={hit.key} role="none">
          <Button
            type="button"
            variant="ghost"
            role="option"
            id={`${hitIdPrefix}-${i}`}
            aria-selected={i === cursor}
            onClick={() => jumpTo(hit)}
            onMouseMove={() => setCursor(i)}
            data-testid={`${testIdPrefix}-search-hit`}
            data-active={i === cursor || undefined}
            className={cn(
              'group h-auto w-full flex-col items-start justify-center gap-0.5 px-2 py-1.5 text-left font-normal whitespace-normal data-[active]:bg-accent data-[active]:text-accent-foreground',
              isMobile ? 'min-h-11' : 'min-h-8',
            )}
          >
            <span className="min-w-0 break-words">{hit.label}</span>
            <span className="text-xs text-muted-foreground group-data-[active]:text-accent-foreground/85">
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
      data-settings-root=""
      className={cn(
        'min-h-0 flex-1',
        isMobile ? 'flex-col gap-3' : 'flex-row gap-6',
      )}
    >
      {isMobile ? (
        mobileNav
      ) : variant === 'page' ? (
        <div className="sticky top-4 flex max-h-[calc(100svh-2rem)] self-start">
          {desktopNav}
        </div>
      ) : (
        desktopNav
      )}
      {body}
    </Tabs>
  );

  const panels = sections.map((s) => (
    <TabsContent
      key={s.value}
      value={s.value}
      ref={(el: HTMLDivElement | null) => {
        if (el) panelEls.current.set(s.value, el);
        else panelEls.current.delete(s.value);
      }}
      forceMount={!s.lazy || visited.has(s.value) ? true : undefined}
      // Radix leaves force-mounted panels visible; hide inactive ones.
      hidden={active !== s.value}
      data-section={s.value}
      className={cn(
        'mx-auto flex w-full max-w-4xl flex-col gap-4',
        '[&_[data-search-hit]]:rounded-md [&_[data-search-hit]]:ring-2 [&_[data-search-hit]]:ring-ring [&_[data-search-hit]]:ring-offset-2 [&_[data-search-hit]]:ring-offset-background',
      )}
    >
      {s.content}
    </TabsContent>
  ));

  return { frame, panels, isMobile };
}

/**
 * Full-screen settings form: a searchable category sidebar (a tab strip on
 * phones) beside the active category's fields.
 */
export function SettingsDialog<V extends string>({
  open,
  sections,
  testIdPrefix,
  loading,
  sectionRef,
  searchPlaceholder,
  ...dialogProps
}: SettingsDialogProps<V>) {
  const isLoading = loading != null && loading !== false;
  const { frame, panels, isMobile } = useSettingsLayout({
    open,
    sections,
    testIdPrefix,
    sectionRef,
    searchPlaceholder,
    variant: 'dialog',
  });

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
      {isLoading ? loading : panels}
    </FormDialog>
  );
}

export interface SettingsPageProps<V extends string = string> {
  sections: SettingsSection<V>[];
  /** Nav items get `${testIdPrefix}-tab-${value}`. */
  testIdPrefix: string;
  /** Search param holding the selected section, so a link can open one. */
  sectionParam?: string;
  sectionRef?: React.Ref<SettingsDialogHandle<V>>;
  searchPlaceholder?: string;
  /** Rendered under the active section, e.g. a save bar. */
  footer?: React.ReactNode;
  className?: string;
  'data-testid'?: string;
}

/** SettingsDialog's sidebar and search laid out on a page instead of in a dialog. */
export function SettingsPage<V extends string>({
  sections,
  testIdPrefix,
  sectionParam = 'section',
  sectionRef,
  searchPlaceholder,
  footer,
  className,
  'data-testid': dataTestId,
}: SettingsPageProps<V>) {
  const [searchParams, setSearchParams] = useSearchParams();
  const first = sections[0].value;
  const onValueChange = React.useCallback(
    (next: V) =>
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev);
          if (next === first) params.delete(sectionParam);
          else params.set(sectionParam, next);
          return params;
        },
        { replace: true, preventScrollReset: true },
      ),
    [setSearchParams, sectionParam, first],
  );
  const { frame, panels } = useSettingsLayout({
    open: true,
    sections,
    testIdPrefix,
    sectionRef,
    searchPlaceholder,
    variant: 'page',
    value: searchParams.get(sectionParam),
    onValueChange,
  });
  return (
    <div className={cn('flex flex-col', className)} data-testid={dataTestId}>
      {frame(
        <div className="min-w-0 flex-1">
          {panels}
          {footer}
        </div>,
      )}
    </div>
  );
}
