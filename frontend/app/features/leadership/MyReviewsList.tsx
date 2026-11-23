import { ChevronDown } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '~/components/ui/collapsible';
import { DisplayName } from '~/components/user/avatar';
import type { OrgFeatureAccess } from '~/features/org-features';
import { getLogger } from '~/lib/logger';
import { cn } from '~/lib/utils';
import { leadershipTrack } from './access';
import { refusalCode, refusalMessage } from './errors';
import { useMyReviews } from './queries';
import type { MyReview } from './schemas';

const log = getLogger('MyReviewsList');

const TRAIT_METRIC_PREFIX = 'rating.';

const VOID_NOTES: Record<MyReview['void_kind'], string | null> = {
  '': null,
  withdrawn: 'Withdrawn',
  lifecycle: 'No longer counted',
  moderated: 'Removed by an organizer',
};

export interface MyReviewsListProps {
  orgId: number;
  access: OrgFeatureAccess;
}

function humanize(key: string): string {
  const text = key.replace(/_/g, ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function useTraitLabels(access: OrgFeatureAccess): Map<string, string> {
  return useMemo(() => {
    const track = leadershipTrack(access);
    const labels = new Map<string, string>();
    for (const metric of track?.metrics ?? []) {
      if (metric.key.startsWith(TRAIT_METRIC_PREFIX))
        labels.set(metric.key.slice(TRAIT_METRIC_PREFIX.length), metric.label);
    }
    return labels;
  }, [access]);
}

function ReviewRow({
  review,
  labels,
}: {
  review: MyReview;
  labels: Map<string, string>;
}) {
  const id = `leadership-mine-${review.event_id}-${review.captain_org_user_id}`;
  const note = VOID_NOTES[review.void_kind];
  return (
    <li className="flex flex-col gap-1 py-2" data-testid={id}>
      <span className="min-w-0 break-words font-medium">
        {DisplayName(review.captain)}
      </span>
      <span className="break-words text-sm text-muted-foreground">
        {review.team_name} · {review.event_name}
      </span>
      {note && (
        <span
          className="text-sm text-muted-foreground"
          data-testid={`${id}-void`}
        >
          {note}
        </span>
      )}
      <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
        {Object.entries(review.scores).map(([key, score]) => (
          <div key={key} className="flex justify-between gap-2">
            <dt className="min-w-0 break-words text-muted-foreground">
              {labels.get(key) ?? humanize(key)}
            </dt>
            <dd className="shrink-0 tabular-nums">{score}</dd>
          </div>
        ))}
      </dl>
    </li>
  );
}

export function MyReviewsList({ orgId, access }: MyReviewsListProps) {
  const [open, setOpen] = useState(false);
  const { data, isLoading, isError, error } = useMyReviews(orgId, access, open);
  const labels = useTraitLabels(access);

  useEffect(() => {
    if (isError)
      log.warn('own captain reviews failed to load', {
        orgId,
        code: refusalCode(error),
      });
  }, [isError, error, orgId]);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <SecondaryButton
          type="button"
          className="min-h-11 w-full justify-between sm:min-h-9 sm:w-auto"
          data-testid="leadership-mine-toggle"
        >
          Your reviews
          <ChevronDown
            aria-hidden="true"
            className={cn('size-4 transition-transform', open && 'rotate-180')}
          />
        </SecondaryButton>
      </CollapsibleTrigger>
      <CollapsibleContent data-testid="leadership-mine">
        {isLoading && (
          <p className="py-2 text-sm text-muted-foreground">
            Loading your reviews...
          </p>
        )}
        {isError && (
          <p className="py-2 text-sm text-destructive">
            {refusalMessage(error)}
          </p>
        )}
        {data && data.length === 0 && (
          <p
            className="py-2 text-sm text-muted-foreground"
            data-testid="leadership-mine-empty"
          >
            You haven&apos;t rated a captain yet.
          </p>
        )}
        {data && data.length > 0 && (
          <ul className="divide-y divide-border">
            {data.map((review) => (
              <ReviewRow
                key={`${review.event_id}-${review.captain_org_user_id}`}
                review={review}
                labels={labels}
              />
            ))}
          </ul>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
