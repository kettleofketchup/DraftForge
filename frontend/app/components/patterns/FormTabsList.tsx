import * as React from 'react';
import { TabsList, TabsTrigger } from '~/components/ui/tabs';
import { cn } from '~/lib/utils';

export interface FormTabItem {
  value: string;
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  /** Marks a tab holding a field with a validation error. */
  invalid?: boolean;
}

interface FormTabsListProps {
  tabs: FormTabItem[];
  /** Triggers get `${testIdPrefix}-tab-${value}`. */
  testIdPrefix: string;
  className?: string;
}

/**
 * Tab strip for tabbed form dialogs: compact wrapping rows below sm, one full
 * width row above. Where that row overflows, the edge with hidden tabs fades
 * and the active tab scrolls into view.
 */
export function FormTabsList({
  tabs,
  testIdPrefix,
  className,
}: FormTabsListProps) {
  const listRef = React.useRef<HTMLDivElement>(null);
  const [fade, setFade] = React.useState({ start: false, end: false });

  const measure = React.useCallback(() => {
    const el = listRef.current;
    if (!el) return;
    const max = el.scrollWidth - el.clientWidth;
    const start = el.scrollLeft > 1;
    const end = el.scrollLeft < max - 1;
    setFade((f) => (f.start === start && f.end === end ? f : { start, end }));
  }, []);

  React.useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    let activeEl: HTMLElement | null = null;
    const reveal = () => {
      const next = el.querySelector<HTMLElement>('[data-state="active"]');
      if (!next || next === activeEl) return;
      activeEl = next;
      if (el.scrollWidth <= el.clientWidth) return;
      const left = next.offsetLeft - (el.clientWidth - next.offsetWidth) / 2;
      el.scrollTo?.({ left: Math.max(0, left) });
      measure();
    };
    reveal();
    measure();
    const mutations = new MutationObserver(reveal);
    mutations.observe(el, {
      subtree: true,
      childList: true,
      attributeFilter: ['data-state'],
    });
    const resize =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(measure);
    resize?.observe(el);
    return () => {
      mutations.disconnect();
      resize?.disconnect();
    };
  }, [measure]);

  return (
    <TabsList
      ref={listRef}
      onScroll={measure}
      data-fade-start={fade.start || undefined}
      data-fade-end={fade.end || undefined}
      className={cn(
        'scroll-fade-x w-full min-h-0 flex-wrap justify-start sm:flex-nowrap overflow-x-auto [scrollbar-width:none] sm:min-h-11 sm:justify-center',
        className,
      )}
    >
      {tabs.map(({ value, label, icon: Icon, invalid }) => (
        <TabsTrigger
          key={value}
          value={value}
          className="min-h-8 flex-none px-3 py-1.5 sm:min-h-10 sm:flex-1 sm:px-4 sm:py-2.5"
          data-testid={`${testIdPrefix}-tab-${value}`}
          data-invalid={invalid || undefined}
        >
          {Icon && <Icon className="h-4 w-4" />}
          {label}
          {invalid && <InvalidDot />}
        </TabsTrigger>
      ))}
    </TabsList>
  );
}

export function InvalidDot({ className }: { className?: string }) {
  return (
    <span
      aria-label="Has errors"
      role="img"
      className={cn('size-2 shrink-0 rounded-full bg-destructive', className)}
    />
  );
}
