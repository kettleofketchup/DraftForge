import { X } from 'lucide-react';
import { useEffect } from 'react';
import { Link } from 'react-router';
import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import { Progress } from '~/components/ui/progress';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import type { TrackDetailProps } from '~/features/standing/panels';
import { formatOrgDate } from '~/features/standing/periods';
import { getLogger } from '~/lib/logger';
import { leadershipAccess } from './access';
import { refusalCode, refusalMessage } from './errors';
import { formatRating, placementLabel } from './format';
import { useLeadershipSettings, useMemberLeadership } from './queries';
import { MIN_EVENT_AGGREGATE_REVIEWS, type EventAggregate } from './schemas';

const log = getLogger('MemberLeadershipPanel');

export type MemberLeadershipPanelProps = Pick<
  TrackDetailProps,
  'orgId' | 'orgUserPk' | 'own' | 'timeZone' | 'access' | 'onClose'
>;

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`;
}

function EventRow({
  event,
  timeZone,
}: {
  event: EventAggregate;
  timeZone: string | undefined;
}) {
  const placement = placementLabel(event.placement);
  const id = `leadership-member-event-${event.event_id}`;
  return (
    <li className="flex flex-col gap-1 py-2" data-testid={id}>
      <div className="flex min-w-0 flex-col gap-1 sm:flex-row sm:items-start sm:justify-between sm:gap-2">
        <Link
          to={`/events/${event.event_id}`}
          className="min-w-0 break-words font-medium hover:underline"
        >
          {event.event_name}
        </Link>
        {!event.released && (
          <Badge
            variant="outline"
            className="w-fit shrink-0"
            data-testid={`${id}-unreleased`}
          >
            Not released
          </Badge>
        )}
      </div>
      <div className="break-words text-sm text-muted-foreground">
        {formatOrgDate(event.scheduled_at, timeZone)}
        {` · ${event.team_name}`}
        {placement && ` · ${placement}`}
        {event.captain_rating_points !== null &&
          ` · +${event.captain_rating_points} rating points`}
      </div>
      {!event.released ? (
        <div className="text-sm text-muted-foreground">
          Only admins see this until the window closes with enough reviews.
        </div>
      ) : event.reviews === null || event.traits === null ? (
        <div className="text-sm text-muted-foreground">
          Fewer than {MIN_EVENT_AGGREGATE_REVIEWS} reviews: per-trait detail
          hidden.
        </div>
      ) : (
        <div className="flex flex-col gap-1 text-sm">
          <div className="text-muted-foreground">
            {plural(event.reviews, 'review')}
            {event.rating !== null &&
              ` · ${formatRating(event.rating)} overall`}
          </div>
          <dl className="grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">
            {event.traits.map((trait) => (
              <div key={trait.key} className="flex justify-between gap-2">
                <dt className="min-w-0 break-words text-muted-foreground">
                  {trait.label}
                </dt>
                <dd className="shrink-0 tabular-nums">
                  {formatRating(trait.average)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </li>
  );
}

export function MemberLeadershipPanel({
  orgId,
  orgUserPk,
  own,
  timeZone,
  access,
  onClose,
}: MemberLeadershipPanelProps) {
  const { data, isLoading, isError, error } = useMemberLeadership(
    orgId,
    access,
    orgUserPk,
  );
  const forbidden = isError && refusalCode(error) === 'not_permitted';
  const { canManage, boardOpen } = leadershipAccess(access);
  // Admins viewing another captain get figures that include unreleased reviews.
  const staffView = canManage && !own;
  // board_open is always true for org staff, so admins read the setting itself;
  // other staff may see the public wording on a private board, never the reverse.
  const settings = useLeadershipSettings(orgId, access, own && canManage);
  const boardPublic = canManage ? settings.data?.leaderboard_public : boardOpen;

  useEffect(() => {
    if (!isError) return;
    if (refusalCode(error) === 'not_permitted') {
      log.warn('leadership member not permitted', { orgId, orgUserPk });
    } else {
      log.error('leadership member failed to load', {
        orgId,
        orgUserPk,
        error,
      });
    }
  }, [isError, error, orgId, orgUserPk]);

  const closeButton = (
    <SecondaryButton
      type="button"
      size="icon"
      className="size-8 shrink-0"
      aria-label="Close leadership details"
      onClick={onClose}
      data-testid="leadership-member-close"
    >
      <X className="h-4 w-4" />
    </SecondaryButton>
  );

  return (
    <section
      className="flex flex-col gap-4 rounded-lg border border-border bg-base-300/40 p-4"
      data-testid="leadership-member"
    >
      <div className="flex items-start justify-between gap-2">
        {data ? (
          <div className="flex min-w-0 items-center gap-2">
            <UserAvatar
              user={{ ...data.member, pk: data.member.user_pk }}
              size="md"
            />
            <h3 className="min-w-0 break-words text-lg font-semibold">
              {DisplayName(data.member)}
            </h3>
          </div>
        ) : (
          <h3 className="text-lg font-semibold">Leadership</h3>
        )}
        {closeButton}
      </div>

      {isLoading && (
        <div className="text-muted-foreground">Loading leadership...</div>
      )}
      {forbidden && (
        <div
          className="text-muted-foreground"
          data-testid="leadership-member-forbidden"
        >
          {refusalMessage(error, 'member')}
        </div>
      )}
      {isError && !forbidden && (
        <div className="text-destructive" data-testid="leadership-member-error">
          {refusalMessage(error, 'member')}
        </div>
      )}

      {data && (
        <>
          {own && boardPublic !== undefined && (
            <p
              className="text-sm text-muted-foreground"
              data-testid="leadership-member-own-note"
            >
              {boardPublic
                ? 'Members can see your rating and points; only you and org admins see the per-event detail.'
                : 'Only you and org admins see this.'}{' '}
              Who rated you is never shown.
            </p>
          )}
          {staffView && (
            <p
              className="text-sm text-muted-foreground"
              data-testid="leadership-member-staff-note"
            >
              Includes unreleased reviews, visible to admins only.
            </p>
          )}

          <div className="flex flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className="text-2xl font-bold tabular-nums"
                data-testid="leadership-member-rating"
              >
                {formatRating(data.rating)}
              </span>
              {data.status === 'new' && (
                <Badge variant="outline" data-testid="leadership-member-new">
                  New
                </Badge>
              )}
            </div>
            <div
              className="text-sm text-muted-foreground"
              data-testid="leadership-member-reviews"
            >
              {staffView
                ? `${plural(data.reviews, 'review')} (includes unreleased)`
                : plural(data.reviews, 'released review')}
            </div>
            {data.status === 'new' && (
              <p className="text-sm text-muted-foreground">
                {staffView
                  ? 'Not enough reviews to be ranked yet.'
                  : 'Not enough released reviews to be ranked yet.'}
              </p>
            )}
            {data.reviews === 0 && data.rating === null && (
              <p
                className="rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground"
                data-testid="leadership-member-unreleased"
              >
                {staffView
                  ? 'No reviews yet.'
                  : 'No released ratings yet. Ratings appear once a review window closes with enough reviews.'}
              </p>
            )}
          </div>

          <div className="flex flex-col gap-1">
            <dl className="grid grid-cols-2 gap-3">
              <div>
                <dt className="text-sm text-muted-foreground">
                  Points all time
                </dt>
                <dd
                  className="text-xl font-semibold tabular-nums"
                  data-testid="leadership-member-points-all"
                >
                  {data.points.all_time}
                </dd>
              </div>
              <div>
                <dt className="text-sm text-muted-foreground">
                  Points this month
                </dt>
                <dd
                  className="text-xl font-semibold tabular-nums"
                  data-testid="leadership-member-points-month"
                >
                  {data.points.this_month}
                </dd>
              </div>
            </dl>
            <p
              className="text-xs text-muted-foreground"
              data-testid="leadership-member-points-note"
            >
              Totals include events still in their review window or without
              enough reviews.
            </p>
          </div>

          {data.traits.some((trait) => trait.rating !== null) && (
            <ul className="flex flex-col gap-2">
              {data.traits.map((trait) => (
                <li
                  key={trait.key}
                  className="flex flex-col gap-1"
                  data-testid={`leadership-member-trait-${trait.key}`}
                >
                  <div className="flex justify-between gap-2 text-sm">
                    <span className="min-w-0 break-words">{trait.label}</span>
                    <span className="shrink-0 tabular-nums">
                      {trait.rating !== null
                        ? formatRating(trait.rating)
                        : staffView
                          ? 'No reviews'
                          : 'Not released'}
                    </span>
                  </div>
                  {trait.rating !== null && (
                    <Progress
                      value={((trait.rating - 1) / 4) * 100}
                      aria-label={trait.label}
                    />
                  )}
                </li>
              ))}
            </ul>
          )}

          {data.events && (
            <div className="flex flex-col gap-1">
              <h4 className="font-semibold">Rated events</h4>
              {data.events.length === 0 ? (
                <div className="text-sm text-muted-foreground">
                  No rated events yet.
                </div>
              ) : (
                <ul className="flex flex-col divide-y divide-border">
                  {data.events.map((event) => (
                    <EventRow
                      key={event.event_id}
                      event={event}
                      timeZone={timeZone}
                    />
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
