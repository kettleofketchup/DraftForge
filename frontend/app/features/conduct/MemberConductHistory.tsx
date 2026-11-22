import { X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import type { OrgFeatureAccess } from '~/features/org-features';
import { formatOrgDate } from '~/features/standing/periods';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { formatShowRate } from './format';
import { OutcomeChip } from './OutcomeChip';
import { useMemberConduct } from './queries';
import {
  HISTORY_PAGE_SIZE,
  OUTCOME_LABELS,
  SOURCE_LABELS,
  WALK_IN_LABEL,
  type ConductHistoryItem,
} from './schemas';

const log = getLogger('MemberConductHistory');

const TOTAL_KEYS = ['attended', 'no_show', 'late_cancel', 'excused'] as const;

export interface MemberConductHistoryProps {
  orgId: number;
  access: OrgFeatureAccess;
  orgUserPk: number;
  timeZone: string | undefined;
  onClose: () => void;
}

function HistoryRow({
  item,
  index,
  timeZone,
}: {
  item: ConductHistoryItem;
  index: number;
  timeZone: string | undefined;
}) {
  const removed = item.event_id === null;
  return (
    <li
      className="flex items-start justify-between gap-3 py-2"
      data-testid={`conduct-history-row-${removed ? `removed-${index}` : item.event_id}`}
    >
      <div className="flex min-w-0 flex-col gap-1">
        <div className="wrap-anywhere font-medium">
          {item.event_id !== null ? (
            <Link to={`/events/${item.event_id}`} className="hover:underline">
              {item.event_name}
            </Link>
          ) : (
            item.event_name
          )}
        </div>
        <div className="text-sm text-muted-foreground">
          {formatOrgDate(item.event_starts_at, timeZone)}
          {` · ${SOURCE_LABELS[item.source]}`}
          {` · Weight ${item.weight.toFixed(2)}`}
        </div>
        {item.set_by && (
          <div
            className="text-sm text-muted-foreground"
            data-testid="conduct-history-set-by"
          >
            Set by{' '}
            {DisplayName({
              pk: item.set_by.user_pk,
              username: item.set_by.username,
            })}
          </div>
        )}
        <div className="flex flex-wrap gap-1">
          {!item.committed && <Badge variant="outline">{WALK_IN_LABEL}</Badge>}
          {removed && <Badge variant="outline">Removed</Badge>}
          {item.voided && <Badge variant="outline">Voided</Badge>}
        </div>
        {item.reason && (
          <div className="text-sm text-muted-foreground">{item.reason}</div>
        )}
      </div>
      <OutcomeChip outcome={item.outcome} className="shrink-0" />
    </li>
  );
}

export function MemberConductHistory({
  orgId,
  access,
  orgUserPk,
  timeZone,
  onClose,
}: MemberConductHistoryProps) {
  const [offset, setOffset] = useState(0);
  const { data, isLoading, isError, error, isPlaceholderData } =
    useMemberConduct(orgId, access, orgUserPk, {
      limit: HISTORY_PAGE_SIZE,
      offset,
    });

  useEffect(() => {
    if (isError)
      log.error('member conduct failed to load', { orgId, orgUserPk, error });
  }, [isError, error, orgId, orgUserPk]);

  const closeButton = (
    <SecondaryButton
      type="button"
      size="icon"
      className="size-8"
      aria-label="Close attendance history"
      onClick={onClose}
      data-testid="conduct-history-close"
    >
      <X className="h-4 w-4" />
    </SecondaryButton>
  );

  return (
    <section
      className="flex flex-col gap-4 rounded-lg border border-border bg-base-300/40 p-4"
      data-testid="conduct-history"
    >
      {data ? (
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <UserAvatar
              user={{ ...data.member, pk: data.member.user_pk }}
              size="md"
            />
            <h3 className="break-words text-lg font-semibold">
              {DisplayName(data.member)}
            </h3>
          </div>
          <div className="flex items-start gap-2">
            <div className="text-right">
              <div
                className="text-2xl font-bold tabular-nums"
                data-testid="conduct-member-score"
              >
                {formatShowRate(data)}
              </div>
              <div
                className="text-xs text-muted-foreground"
                data-testid="conduct-member-basis"
              >
                Based on {data.counted_events} counted{' '}
                {data.counted_events === 1 ? 'event' : 'events'} (
                {data.weighted_events.toFixed(1)} after recency weighting)
              </div>
            </div>
            {closeButton}
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-lg font-semibold">Attendance</h3>
          {closeButton}
        </div>
      )}

      {isLoading && (
        <div className="text-muted-foreground">Loading attendance...</div>
      )}
      {isError && (
        <div className="text-destructive" data-testid="conduct-history-error">
          {extractApiError(error) ?? 'Could not load attendance history.'}
        </div>
      )}

      {data && (
        <>
          {data.status === 'new' && (
            <p
              className="rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground"
              data-testid="conduct-new-member"
            >
              New members are shown as New until they have enough counted
              events. Until then the rate leans on the organization&apos;s
              baseline.
            </p>
          )}
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {TOTAL_KEYS.map((key) => (
              <div key={key}>
                <dt className="text-sm text-muted-foreground">
                  {OUTCOME_LABELS[key]}
                </dt>
                <dd
                  className="text-xl font-semibold tabular-nums"
                  data-testid={`conduct-total-${key}`}
                >
                  {data.totals[key]}
                </dd>
              </div>
            ))}
          </dl>

          {data.history.length === 0 && offset === 0 ? (
            <div
              className="text-sm text-muted-foreground"
              data-testid="conduct-history-empty"
            >
              No attendance recorded yet.
            </div>
          ) : (
            <ul className="flex flex-col divide-y divide-border">
              {data.history.map((item, index) => (
                <HistoryRow
                  key={`${item.event_id ?? 'removed'}-${offset + index}`}
                  item={item}
                  index={offset + index}
                  timeZone={timeZone}
                />
              ))}
            </ul>
          )}

          {(offset > 0 || data.history.length === HISTORY_PAGE_SIZE) && (
            <div className="flex items-center justify-end gap-2">
              <SecondaryButton
                size="sm"
                className="min-h-11 sm:min-h-8"
                disabled={offset === 0 || isPlaceholderData}
                onClick={() =>
                  setOffset((o) => Math.max(0, o - HISTORY_PAGE_SIZE))
                }
                data-testid="conduct-history-prev"
              >
                Newer
              </SecondaryButton>
              <SecondaryButton
                size="sm"
                className="min-h-11 sm:min-h-8"
                disabled={
                  data.history.length < HISTORY_PAGE_SIZE || isPlaceholderData
                }
                onClick={() => setOffset((o) => o + HISTORY_PAGE_SIZE)}
                data-testid="conduct-history-next"
              >
                Older
              </SecondaryButton>
            </div>
          )}
        </>
      )}
    </section>
  );
}
