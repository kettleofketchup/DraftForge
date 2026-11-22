import { Clock } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '~/components/ui/card';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import type { OrgFeatureAccess } from '~/features/org-features';
import { getLogger } from '~/lib/logger';
import { CaptainReviewDialog } from './CaptainReviewDialog';
import { formatCountdown, useCountdown } from './countdown';
import { refusalCode } from './errors';
import { usePendingReviews } from './queries';
import { reviewAction } from './reviewState';
import type { PendingReview } from './schemas';

const log = getLogger('PendingReviewsCard');

export interface PendingReviewsCardProps {
  orgId: number;
  access: OrgFeatureAccess;
  eventId?: number | null;
  testIdPrefix?: string;
}

export function pendingCount(items: PendingReview[]): number {
  return items.filter((item) => reviewAction(item).state === 'todo').length;
}

function itemKey(item: PendingReview): string {
  return `${item.event_id}-${item.captain_org_user_id}`;
}

function Countdown({ iso }: { iso: string }) {
  const { msLeft } = useCountdown(iso);
  return (
    <span className="flex items-center gap-1">
      <Clock aria-hidden="true" className="size-3.5 shrink-0" />
      {formatCountdown(msLeft)}
    </span>
  );
}

function PendingItem({
  item,
  prefix,
  onOpen,
}: {
  item: PendingReview;
  prefix: string;
  onOpen: () => void;
}) {
  const action = reviewAction(item);
  const id = itemKey(item);
  return (
    <li
      className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center"
      data-testid={`${prefix}-item-${id}`}
    >
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <UserAvatar
          user={{ ...item.captain, pk: item.captain.user_pk }}
          size="sm"
        />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:gap-2">
            <span className="min-w-0 flex-1 break-words font-medium">
              {DisplayName(item.captain)}
            </span>
            {action.badge && (
              <Badge
                variant="outline"
                className="w-fit shrink-0"
                data-testid={`${prefix}-badge-${id}`}
              >
                {action.badge}
              </Badge>
            )}
          </div>
          <span className="break-words text-sm text-muted-foreground">
            {item.team_name} · {item.event_name}
          </span>
          <span className="text-sm text-muted-foreground">
            <Countdown iso={item.window_closes_at} />
          </span>
        </div>
      </div>
      <SecondaryButton
        type="button"
        className="min-h-11 w-full shrink-0 sm:min-h-9 sm:w-auto"
        onClick={onOpen}
        data-testid={`${prefix}-open-${id}`}
      >
        {action.label}
      </SecondaryButton>
    </li>
  );
}

export function PendingReviewsCard({
  orgId,
  access,
  eventId = null,
  testIdPrefix = 'leadership-pending',
}: PendingReviewsCardProps) {
  const { data, isError, error } = usePendingReviews(orgId, access, eventId);
  const [openKey, setOpenKey] = useState<string | null>(null);

  useEffect(() => {
    if (isError)
      log.warn('pending captain reviews failed to load', {
        orgId,
        eventId,
        code: refusalCode(error),
      });
  }, [isError, error, orgId, eventId]);

  if (isError || !data || data.length === 0) return null;
  const opened = data.find((item) => itemKey(item) === openKey) ?? null;
  const count = pendingCount(data);

  return (
    <Card data-testid={testIdPrefix}>
      <CardHeader>
        <div className="flex items-center gap-2">
          <CardTitle role="heading" aria-level={3}>
            Rate your captain
          </CardTitle>
          <Badge
            variant="secondary"
            className="shrink-0"
            data-testid={`${testIdPrefix}-count`}
          >
            {count}
            <span className="sr-only"> to rate</span>
          </Badge>
        </div>
        <CardDescription>
          Score how your captain led the team. Captains never see who rated
          them.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="divide-y divide-border">
          {data.map((item) => (
            <PendingItem
              key={itemKey(item)}
              item={item}
              prefix={testIdPrefix}
              onOpen={() => setOpenKey(itemKey(item))}
            />
          ))}
        </ul>
      </CardContent>
      {opened && (
        <CaptainReviewDialog
          orgId={orgId}
          access={access}
          review={opened}
          open
          onOpenChange={(open) => {
            if (!open) setOpenKey(null);
          }}
        />
      )}
    </Card>
  );
}
