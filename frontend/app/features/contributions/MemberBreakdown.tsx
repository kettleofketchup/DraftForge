import { X } from 'lucide-react';
import { Link } from 'react-router';
import { SecondaryButton } from '~/components/ui/buttons';
import { UserAvatar } from '~/components/user/UserAvatar';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { useMemberBreakdown } from './queries';
import { KIND_LABELS, type MonthPoints } from './schemas';
import { formatOrgDate, monthLabel, shortMonthLabel } from './timezone';

export interface MemberBreakdownProps {
  orgId: number;
  orgUserPk: number;
  period: string;
  timeZone: string | undefined;
  access: OrgFeatureAccess;
  onClose: () => void;
}

function MonthlyBars({ monthly }: { monthly: MonthPoints[] }) {
  const max = Math.max(1, ...monthly.map((m) => m.points));
  return (
    <figure data-testid="contributions-monthly">
      <figcaption className="mb-2 text-sm text-muted-foreground">
        Points per month
      </figcaption>
      <div
        className="flex h-32 items-end gap-0.5 border-b border-border"
        role="list"
      >
        {monthly.map((m) => (
          <div
            key={m.month}
            role="listitem"
            className="group relative flex h-full flex-1 items-end"
            title={`${monthLabel(m.month)}: ${m.points} points`}
            aria-label={`${monthLabel(m.month)}: ${m.points} points`}
          >
            <div
              className="w-full rounded-t bg-primary/80 transition-colors group-hover:bg-primary"
              style={{ height: `${(Math.max(0, m.points) / max) * 100}%` }}
            />
          </div>
        ))}
      </div>
      <div
        className="mt-1 flex gap-0.5 text-[10px] text-muted-foreground"
        aria-hidden="true"
      >
        {monthly.map((m) => (
          <span key={m.month} className="flex-1 text-center">
            {shortMonthLabel(m.month)}
          </span>
        ))}
      </div>
    </figure>
  );
}

export function MemberBreakdown({
  orgId,
  orgUserPk,
  period,
  timeZone,
  access,
  onClose,
}: MemberBreakdownProps) {
  const { data, isLoading, isError, error } = useMemberBreakdown(
    orgId,
    access,
    orgUserPk,
    period,
  );

  return (
    <section
      className="flex flex-col gap-4 rounded-lg border border-border bg-base-300/40 p-4"
      data-testid="contributions-breakdown"
    >
      <div className="flex items-center justify-between gap-2">
        {data ? (
          <div className="flex items-center gap-2">
            <UserAvatar
              user={{
                pk: data.member.user_pk,
                username: data.member.username,
                nickname: data.member.nickname,
                avatarUrl: data.member.avatarUrl,
              }}
              size="md"
            />
            <h3 className="text-lg font-semibold">
              {data.member.nickname || data.member.username}
            </h3>
          </div>
        ) : (
          <h3 className="text-lg font-semibold">Breakdown</h3>
        )}
        <SecondaryButton
          type="button"
          size="icon"
          className="size-8"
          aria-label="Close breakdown"
          onClick={onClose}
          data-testid="contributions-breakdown-close"
        >
          <X className="h-4 w-4" />
        </SecondaryButton>
      </div>

      {isLoading && (
        <div className="text-muted-foreground">Loading breakdown...</div>
      )}
      {isError && (
        <div
          className="text-destructive"
          data-testid="contributions-breakdown-error"
        >
          {extractApiError(error) ?? 'Could not load this breakdown.'}
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-sm text-muted-foreground">All time</div>
              <div
                className="text-2xl font-bold tabular-nums"
                data-testid="contributions-member-all-time"
              >
                {data.totals.all_time.toLocaleString('en-US')}
              </div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">This month</div>
              <div
                className="text-2xl font-bold tabular-nums"
                data-testid="contributions-member-this-month"
              >
                {data.totals.this_month.toLocaleString('en-US')}
              </div>
            </div>
          </div>

          {data.monthly.length > 0 && <MonthlyBars monthly={data.monthly} />}

          {data.entries.length === 0 ? (
            <div className="text-sm text-muted-foreground">
              No entries in this period
            </div>
          ) : (
            <ul className="flex flex-col divide-y divide-border">
              {data.entries.map((entry) => (
                <li
                  key={entry.pk}
                  className="flex items-start justify-between gap-3 py-2"
                  data-testid={`contributions-entry-${entry.pk}`}
                >
                  <div className="min-w-0">
                    <div className="font-medium">{KIND_LABELS[entry.kind]}</div>
                    <div className="truncate text-sm text-muted-foreground">
                      {formatOrgDate(entry.occurred_at, timeZone)}
                      {entry.event ? (
                        <>
                          {' · '}
                          <Link
                            to={`/events/${entry.event.id}`}
                            className="hover:underline"
                          >
                            {entry.event.name}
                          </Link>
                        </>
                      ) : entry.event_name ? (
                        ` · ${entry.event_name}`
                      ) : null}
                    </div>
                    {entry.reason && (
                      <div className="text-sm text-muted-foreground">
                        {entry.reason}
                      </div>
                    )}
                  </div>
                  <div className="shrink-0 font-semibold tabular-nums">
                    +{entry.points}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
