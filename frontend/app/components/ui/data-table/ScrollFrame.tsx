import { useEffect, useRef, useState, type ReactNode } from 'react';

import { cn } from '~/lib/utils';

export interface ScrollFrameProps {
  testId?: string;
  label?: string;
  className?: string;
  children: ReactNode;
}

/** Sideways scroller (a named, focusable region) with an edge fade while content sits past the right edge. */
export function ScrollFrame({
  testId,
  label,
  className,
  children,
}: ScrollFrameProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [more, setMore] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const update = () =>
      setMore(el.scrollLeft + el.clientWidth < el.scrollWidth - 1);
    update();
    el.addEventListener('scroll', update, { passive: true });
    const ro =
      typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(update);
    ro?.observe(el);
    const table = el.querySelector('table');
    if (table) ro?.observe(table);
    return () => {
      el.removeEventListener('scroll', update);
      ro?.disconnect();
    };
  }, []);
  return (
    <div className={cn('relative', className)}>
      <div
        ref={ref}
        data-testid={testId}
        role="region"
        aria-label={label}
        tabIndex={0}
        className="overflow-x-auto overscroll-x-contain rounded-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring [&_[data-slot=table-container]]:overflow-visible"
      >
        {children}
      </div>
      <div
        aria-hidden
        data-testid={testId && `${testId}-fade`}
        data-visible={more ? 'true' : 'false'}
        className={cn(
          'pointer-events-none absolute inset-y-0 right-0 w-12 rounded-r-md bg-linear-to-l from-card via-card/80 to-transparent transition-opacity',
          more ? 'opacity-100' : 'opacity-0',
        )}
      />
    </div>
  );
}
