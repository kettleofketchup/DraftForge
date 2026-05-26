import { Link } from 'react-router';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '~/components/ui/breadcrumb';
import { EntityIcon } from '~/components/ui/entity-icons';
import { cn } from '~/lib/utils';

const TYPE_CONFIG: Record<EntityType, { label: string; listHref: string }> = {
  organization: { label: 'Organization', listHref: '/organizations' },
  league: { label: 'League', listHref: '/leagues' },
  'event-series': { label: 'Event Series', listHref: '/events' },
  event: { label: 'Event', listHref: '/events' },
  tournament: { label: 'Tournament', listHref: '/tournaments' },
};

export type EntityType = 'organization' | 'league' | 'event-series' | 'event' | 'tournament';

export interface BreadcrumbSegment {
  type: EntityType;
  label: string;
  href?: string;
}

interface EntityBreadcrumbProps {
  segments: BreadcrumbSegment[];
  /**
   * When set, every `segments` item renders as a link (using its `href`) and
   * `currentLabel` is appended as the trailing non-clickable BreadcrumbPage.
   * Use this on sub-pages of an entity (e.g. rollcall is a sub-page of an
   * event — pass the event in `segments` and `currentLabel="Roll Call"` so
   * the event remains clickable).
   *
   * When omitted, the last `segments` item is treated as the current page and
   * rendered non-clickable — the original behavior used by entity detail pages.
   */
  currentLabel?: string;
  className?: string;
}

export function EntityBreadcrumb({ segments, currentLabel, className }: EntityBreadcrumbProps) {
  if (segments.length === 0 && !currentLabel) return null;

  // When currentLabel is set, every segment is a link; otherwise the last
  // segment is the current page (non-clickable).
  const treatLastAsCurrent = !currentLabel;

  return (
    <Breadcrumb className={cn('mb-2 hidden sm:block', className)}>
      <BreadcrumbList>
        {segments.map((segment, index) => {
          const isLastSegment = index === segments.length - 1;
          const renderAsCurrent = treatLastAsCurrent && isLastSegment;
          const showSeparator = !isLastSegment || !!currentLabel;
          return (
            <span key={`${segment.type}-${index}`} className="contents">
              <BreadcrumbItem className="flex flex-col items-start gap-0">
                <BreadcrumbLink asChild>
                  <Link
                    to={TYPE_CONFIG[segment.type].listHref}
                    className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wider font-medium leading-none"
                  >
                    <EntityIcon type={segment.type} size="xs" />
                    {TYPE_CONFIG[segment.type].label}
                  </Link>
                </BreadcrumbLink>
                {renderAsCurrent || !segment.href ? (
                  <BreadcrumbPage className="text-sm font-medium">
                    {segment.label}
                  </BreadcrumbPage>
                ) : (
                  <BreadcrumbLink asChild>
                    <Link to={segment.href} className="text-sm">
                      {segment.label}
                    </Link>
                  </BreadcrumbLink>
                )}
              </BreadcrumbItem>
              {showSeparator && <BreadcrumbSeparator />}
            </span>
          );
        })}
        {currentLabel && (
          <BreadcrumbItem className="flex flex-col items-start gap-0">
            <span className="text-[10px] uppercase tracking-wider font-medium leading-none text-muted-foreground">
              Page
            </span>
            <BreadcrumbPage className="text-sm font-medium">
              {currentLabel}
            </BreadcrumbPage>
          </BreadcrumbItem>
        )}
      </BreadcrumbList>
    </Breadcrumb>
  );
}
