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
  className?: string;
}

export function EntityBreadcrumb({ segments, className }: EntityBreadcrumbProps) {
  if (segments.length === 0) return null;

  return (
    <Breadcrumb className={cn('mb-2', className)}>
      <BreadcrumbList>
        {segments.map((segment, index) => {
          const isLast = index === segments.length - 1;
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
                {isLast || !segment.href ? (
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
              {!isLast && <BreadcrumbSeparator />}
            </span>
          );
        })}
      </BreadcrumbList>
    </Breadcrumb>
  );
}
