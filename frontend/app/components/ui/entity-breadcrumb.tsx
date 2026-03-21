import { Link } from 'react-router';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '~/components/ui/breadcrumb';
import { cn } from '~/lib/utils';

const TYPE_LABELS: Record<EntityType, string> = {
  organization: 'Organization',
  league: 'League',
  'event-series': 'Event Series',
  event: 'Event',
  tournament: 'Tournament',
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
                <span className="text-[10px] uppercase tracking-wider text-muted-foreground/60 font-medium leading-none">
                  {TYPE_LABELS[segment.type]}
                </span>
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
