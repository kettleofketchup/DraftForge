import * as React from 'react';
import {
  useFormState,
  type FieldErrors,
  type FieldValues,
  type UseFormReturn,
} from 'react-hook-form';
import { toast } from 'sonner';
import { FormDialog } from '~/components/ui/dialogs';
import { Form } from '~/components/ui/form';
import { Tabs, TabsContent } from '~/components/ui/tabs';
import {
  buildSettingsIndex,
  resolveFieldSection,
  scanFieldPlacements,
  searchSettings,
  sectionsWithErrors,
  type FieldPlacements,
  type SettingsIndexEntry,
} from './settingsSearch';
import { SettingsSidebar } from './SettingsSidebar';
import { EVENT_TAB_META, type EventFormTabValue } from './tabs';

export interface EventFormTab {
  value: EventFormTabValue;
  content: React.ReactNode;
  /** Mount on first visit, then stay mounted. */
  lazy?: boolean;
}

export interface EventFormDialogHandle {
  selectTab: (value: EventFormTabValue) => void;
}

export interface EventFormDialogProps<
  TIn extends FieldValues,
  TOut extends FieldValues,
> {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  submitLabel: string;
  form: UseFormReturn<TIn, unknown, TOut>;
  onValid: (data: TOut) => void | Promise<void>;
  isSubmitting: boolean;
  tabs: EventFormTab[];
  /** Section items get `${tabTestIdPrefix}-tab-${value}`. */
  tabTestIdPrefix: string;
  /** Rendered instead of the sections when set. */
  loading?: React.ReactNode;
  tabRef?: React.Ref<EventFormDialogHandle>;
  'data-testid'?: string;
}

const HIT_MS = 2000;

const FOCUSABLE =
  'input:not([type="hidden"]), textarea, select, button, [role="combobox"], [tabindex]:not([tabindex="-1"])';

function placementsKey(p: FieldPlacements): string {
  return [...p]
    .map(
      ([f, x]) =>
        `${f}\u0000${x.section}\u0000${x.label}\u0000${x.description}`,
    )
    .join('\u0001');
}

function isEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
  );
}

/** Full-screen dialog with a searchable section sidebar, shared by the event, series and defaults forms. */
export function EventFormDialog<
  TIn extends FieldValues,
  TOut extends FieldValues,
>({
  open,
  onOpenChange,
  title,
  description,
  submitLabel,
  form,
  onValid,
  isSubmitting,
  tabs,
  tabTestIdPrefix,
  loading,
  tabRef,
  'data-testid': dataTestId,
}: EventFormDialogProps<TIn, TOut>) {
  const first = tabs[0].value;
  const available = tabs.map((t) => t.value);
  const [tab, setTab] = React.useState<EventFormTabValue>(first);
  const [visited, setVisited] = React.useState<Set<EventFormTabValue>>(
    () => new Set([first]),
  );
  const [query, setQuery] = React.useState('');
  // A fresh object per pick, so picking the same field twice jumps again.
  const [jump, setJump] = React.useState<{
    field: string;
    section: EventFormTabValue;
  } | null>(null);
  const [placements, setPlacements] = React.useState<FieldPlacements>(
    () => new Map(),
  );
  const [wasOpen, setWasOpen] = React.useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setTab(first);
      setVisited(new Set([first]));
      setQuery('');
    }
  }

  const panelsRef = React.useRef<HTMLDivElement>(null);
  const searchRef = React.useRef<HTMLInputElement>(null);

  const selectTab = React.useCallback((value: EventFormTabValue) => {
    setTab(value);
    setVisited((prev) => (prev.has(value) ? prev : new Set(prev).add(value)));
  }, []);
  React.useImperativeHandle(tabRef, () => ({ selectTab }), [selectTab]);

  // Where each field renders decides its section for search and error routing.
  React.useLayoutEffect(() => {
    if (!panelsRef.current) return;
    const next = scanFieldPlacements(panelsRef.current);
    setPlacements((prev) =>
      placementsKey(prev) === placementsKey(next) ? prev : next,
    );
  });

  const { errors } = useFormState({ control: form.control });
  const errorSections = sectionsWithErrors(
    Object.keys(errors),
    placements,
    available,
  );

  const groups = React.useMemo(() => {
    if (!query.trim()) return [];
    const index = buildSettingsIndex({
      sections: tabs.map((t) => ({
        value: t.value,
        mounted: !t.lazy || visited.has(t.value),
      })),
      placements,
    });
    return searchSettings(index, available, query);
    // `available` derives from `tabs`.
  }, [query, tabs, visited, placements]);

  const pickResult = (entry: SettingsIndexEntry) => {
    selectTab(entry.section);
    setQuery('');
    setJump({ field: entry.field, section: entry.section });
  };

  React.useEffect(() => {
    if (!jump) return;
    const root = panelsRef.current;
    const row =
      root?.querySelector<HTMLElement>(
        `[data-section="${jump.section}"] [data-field="${jump.field}"]`,
      ) ?? root?.querySelector<HTMLElement>(`[data-field="${jump.field}"]`);
    if (!row) return;
    const reduce = window.matchMedia?.(
      '(prefers-reduced-motion: reduce)',
    ).matches;
    row.scrollIntoView?.({
      block: 'center',
      behavior: reduce ? 'auto' : 'smooth',
    });
    row.setAttribute('data-search-hit', '');
    row.querySelector<HTMLElement>(FOCUSABLE)?.focus({ preventScroll: true });
    const timer = window.setTimeout(
      () => row.removeAttribute('data-search-hit'),
      HIT_MS,
    );
    return () => {
      window.clearTimeout(timer);
      row.removeAttribute('data-search-hit');
    };
  }, [jump]);

  React.useEffect(() => {
    if (!open || loading) return;
    const onKeyDown = (e: KeyboardEvent) => {
      const slash =
        e.key === '/' &&
        !e.ctrlKey &&
        !e.metaKey &&
        !e.altKey &&
        !isEditable(e.target);
      const k = e.key.toLowerCase() === 'k' && (e.ctrlKey || e.metaKey);
      if (!slash && !k) return;
      if (
        document.querySelector(
          '[data-state="open"][role="listbox"], [data-state="open"][role="menu"]',
        )
      )
        return;
      e.preventDefault();
      searchRef.current?.focus();
      searchRef.current?.select();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open, loading]);

  const onInvalid = (invalid: FieldErrors<TIn>) => {
    const [key, error] = Object.entries(invalid)[0] ?? [];
    if (!key) return;
    setQuery('');
    selectTab(resolveFieldSection(key, placements, available));
    const message = (error as { message?: unknown } | undefined)?.message;
    toast.error('Please fix the highlighted fields', {
      description: typeof message === 'string' ? message : undefined,
    });
  };

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      submitLabel={submitLabel}
      isSubmitting={isSubmitting}
      onSubmit={form.handleSubmit(onValid, onInvalid)}
      size="screen"
      // Radix would focus the search box, opening the keyboard on phones.
      autoFocus={false}
      data-testid={dataTestId}
    >
      {loading ?? (
        <Form {...form}>
          <Tabs
            value={tab}
            onValueChange={(v) => selectTab(v as EventFormTabValue)}
            orientation="vertical"
            className="gap-4 md:flex-row md:items-start md:gap-6"
          >
            <SettingsSidebar
              sections={tabs.map((t) => ({
                value: t.value,
                ...EVENT_TAB_META[t.value],
                hasError: errorSections.has(t.value),
              }))}
              active={tab}
              onSelect={selectTab}
              query={query}
              onQueryChange={setQuery}
              groups={groups}
              onPick={pickResult}
              testIdPrefix={tabTestIdPrefix}
              searchRef={searchRef}
            />
            <div
              ref={panelsRef}
              className="min-w-0 flex-1 [&_[data-search-hit]]:rounded-md [&_[data-search-hit]]:bg-primary/10 [&_[data-search-hit]]:ring-2 [&_[data-search-hit]]:ring-primary [&_[data-search-hit]]:ring-offset-2 [&_[data-search-hit]]:ring-offset-background"
            >
              {tabs.map((t) => (
                <TabsContent
                  key={t.value}
                  value={t.value}
                  data-section={t.value}
                  forceMount={
                    !t.lazy || visited.has(t.value) ? true : undefined
                  }
                  // Radix leaves force-mounted panels visible; hide inactive ones.
                  hidden={tab !== t.value}
                  className="mx-auto flex w-full max-w-4xl flex-col gap-4"
                >
                  {t.content}
                </TabsContent>
              ))}
            </div>
          </Tabs>
        </Form>
      )}
    </FormDialog>
  );
}
