/**
 * VirtualizedUserGrid - row-virtualized responsive grid of UserCards.
 *
 * Replaces the previous progressive-render approach: instead of mounting
 * every card and clipping painted output via content-visibility, we use
 * @tanstack/react-virtual to render only the rows that intersect the
 * viewport (plus an overscan buffer). The total scroll height is preserved
 * so the page scrollbar feels right; only ~30-40 cards stay mounted at once
 * regardless of total user count.
 *
 * Column count is derived from the grid container's actual width via a
 * ResizeObserver, not from window.matchMedia, so the component works
 * correctly inside tab panels and constrained layouts.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';

import type { UserClassType, UserType } from '~/components/user/types';
import { UserCard } from '~/components/user/userCard';

/**
 * The whole app scrolls inside `<ScrollArea id="outlet_root">` (root.tsx:98),
 * a Radix ScrollArea. The body doesn't scroll, so document.scrollingElement
 * is the wrong target for `getScrollElement`. Radix renders the actual
 * scrolling viewport as a child div with `[data-radix-scroll-area-viewport]`.
 * Resolve it lazily on first call so SSR doesn't try to access window.
 */
function getOutletScrollElement(): HTMLElement | null {
  if (typeof document === 'undefined') return null;
  const root = document.getElementById('outlet_root');
  if (!root) return (document.scrollingElement as HTMLElement) ?? null;
  // shadcn's ScrollArea renders the inner Radix viewport with
  // data-slot="scroll-area-viewport". That's the actual scrolling element
  // — listen there. Fall back to the root if it hasn't mounted yet.
  return (
    root.querySelector<HTMLElement>('[data-slot="scroll-area-viewport"]') ?? root
  );
}

/** Min container width → column count breakpoints (mobile-first). */
export interface ColumnBreakpoints {
  /** Default (< sm). */
  base: number;
  /** ≥ 640px */
  sm?: number;
  /** ≥ 768px */
  md?: number;
  /** ≥ 1024px */
  lg?: number;
  /** ≥ 1280px */
  xl?: number;
  /** ≥ 1536px */
  '2xl'?: number;
}

const DEFAULT_BREAKPOINTS: ColumnBreakpoints = {
  base: 1,
  md: 2,
  lg: 3,
  xl: 4,
};

function pickColumns(width: number, bp: ColumnBreakpoints): number {
  if (bp['2xl'] !== undefined && width >= 1536) return bp['2xl'];
  if (bp.xl !== undefined && width >= 1280) return bp.xl;
  if (bp.lg !== undefined && width >= 1024) return bp.lg;
  if (bp.md !== undefined && width >= 768) return bp.md;
  if (bp.sm !== undefined && width >= 640) return bp.sm;
  return bp.base;
}

interface Props {
  users: UserType[];
  /** Map of min container-width → column count. Mobile-first. */
  cols?: ColumnBreakpoints;
  /** Estimated row height in px (used until cards render and measure). */
  estimatedRowHeight?: number;
  /** Number of off-screen rows to keep mounted on each side. */
  overscan?: number;
  /** Forwarded to UserCard. */
  compact?: boolean;
  /** Forwarded to UserCard. */
  deleteButtonType?: 'normal' | 'tournament';
  /** Forwarded to UserCard. */
  organizationId?: number;
  /** Forwarded to UserCard. */
  leagueId?: number;
}

export function VirtualizedUserGrid({
  users,
  cols = DEFAULT_BREAKPOINTS,
  estimatedRowHeight = 320,
  overscan = 3,
  compact,
  deleteButtonType,
  organizationId,
  leagueId,
}: Props) {
  const parentRef = useRef<HTMLDivElement | null>(null);
  const [columns, setColumns] = useState(() => cols.base);

  // Track the grid container's width so we can pick the right column count
  // even when the grid is inside a tab/sidebar/constrained layout.
  useEffect(() => {
    const el = parentRef.current;
    if (!el) return;
    const update = () => setColumns(pickColumns(el.clientWidth, cols));
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [cols]);

  const rowCount = Math.max(1, Math.ceil(users.length / columns));

  // The app scrolls inside the Radix ScrollArea viewport (see helper above),
  // NOT on the document body. We resolve that element so the virtualizer
  // listens to the right scroll events.
  const [scrollElement, setScrollElement] = useState<HTMLElement | null>(null);
  useEffect(() => {
    setScrollElement(getOutletScrollElement());
  }, []);

  // Compute the grid's offset within the scrolling viewport so the
  // virtualizer's translateY positions line up with actual scroll position.
  const [scrollMargin, setScrollMargin] = useState(0);
  useEffect(() => {
    const grid = parentRef.current;
    if (!grid || !scrollElement) return;
    const update = () => {
      const gridRect = grid.getBoundingClientRect();
      const scrollRect = scrollElement.getBoundingClientRect();
      // Offset of the grid top from the scroll viewport top, plus current
      // scrollTop so the result is independent of where we are right now.
      setScrollMargin(gridRect.top - scrollRect.top + scrollElement.scrollTop);
    };
    update();
    // Window resize and content above the grid changing height both shift it.
    const ro = new ResizeObserver(update);
    ro.observe(grid);
    if (grid.parentElement) ro.observe(grid.parentElement);
    return () => ro.disconnect();
  }, [scrollElement]);

  const virtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => scrollElement,
    estimateSize: () => estimatedRowHeight,
    overscan,
    scrollMargin,
  });

  const virtualRows = virtualizer.getVirtualItems();

  // Pre-slice user pages by row so the inner JSX is straightforward.
  const rowsOfUsers = useMemo(() => {
    const rows: UserType[][] = [];
    for (let i = 0; i < rowCount; i++) {
      rows.push(users.slice(i * columns, (i + 1) * columns));
    }
    return rows;
  }, [users, columns, rowCount]);

  return (
    <div
      ref={parentRef}
      className="w-full"
      style={{
        // Reserve the full virtualized height so page scroll length is correct.
        height: virtualizer.getTotalSize(),
        position: 'relative',
      }}
    >
      {virtualRows.map((virtualRow) => {
        const rowUsers = rowsOfUsers[virtualRow.index] ?? [];
        return (
          <div
            key={virtualRow.key}
            ref={virtualizer.measureElement}
            data-index={virtualRow.index}
            className="grid gap-6 md:gap-8 lg:gap-10"
            style={{
              gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              transform: `translateY(${virtualRow.start - virtualizer.options.scrollMargin}px)`,
              paddingBottom: '1rem',
            }}
          >
            {rowUsers.map((u, idx) => (
              <UserCard
                key={`uc-${u.pk}`}
                user={u as UserClassType}
                saveFunc="save"
                deleteButtonType={deleteButtonType ?? 'normal'}
                animationIndex={virtualRow.index * columns + idx}
                compact={compact}
                organizationId={organizationId}
                leagueId={leagueId}
              />
            ))}
          </div>
        );
      })}
    </div>
  );
}
