import type { ReactNode } from 'react';
import { cn } from '~/lib/utils';

/**
 * Shared page header for entity detail routes (events, tournaments, leagues,
 * organizations, …). Centers the title + inline badge on mobile, left-aligns
 * at sm+. Mobile font size is deliberately small (text-base, font-semibold)
 * so long entity names don't dominate iPhone-SE-width viewports.
 *
 * @example
 *   <PageHeader
 *     title={event.name}
 *     badge={<EventStateBadge state={event.state} />}
 *     subtitle={<Badge>…date pill…</Badge>}
 *   />
 */
export interface PageHeaderProps {
  /** Primary entity name. Rendered as the h1 of the page. */
  title: string;
  /** Inline pill/status indicator that sits beside the title (state badge, etc). */
  badge?: ReactNode;
  /** Secondary metadata rendered below the title (e.g. a date pill). */
  subtitle?: ReactNode;
  /** Action buttons (Edit/Delete/RSVP) rendered below the subtitle. */
  actions?: ReactNode;
  /** Optional className applied to the outer wrapper. */
  className?: string;
  /** data-testid forwarded to the h1 so Playwright can target the title. */
  'data-testid'?: string;
}

export function PageHeader({
  title,
  badge,
  subtitle,
  actions,
  className,
  'data-testid': testId,
}: PageHeaderProps) {
  return (
    <div className={cn('space-y-2 sm:space-y-4', className)}>
      {/* Title row: centered + stacked on mobile, inline + left-aligned at sm+ */}
      <div className="flex flex-col items-center text-center gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-3 sm:gap-y-1 sm:text-left">
        <h1
          className="text-base sm:text-lg md:text-2xl lg:text-4xl font-semibold md:font-bold break-normal hyphens-none leading-tight tracking-tight text-foreground"
          data-testid={testId}
        >
          {title}
        </h1>
        {badge}
      </div>

      {subtitle && (
        <div className="flex justify-center sm:justify-start">{subtitle}</div>
      )}

      {actions && <div>{actions}</div>}
    </div>
  );
}
