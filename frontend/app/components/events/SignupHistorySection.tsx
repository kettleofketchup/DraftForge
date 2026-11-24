import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { ZodError } from 'zod';

import {
  SIGNUP_LEDGER_ACTIONS,
  type HistorySubject,
} from '~/components/events/schemas';
import {
  SIGNUP_ACTION_LABELS,
  originalSignupId,
} from '~/components/events/signupHistory';
import {
  BrandSelect,
  BrandSelectContent,
  BrandSelectItem,
  BrandSelectTrigger,
  SelectValue,
} from '~/components/ui/brand-select';
import { SecondaryButton } from '~/components/ui/buttons';
import { Skeleton } from '~/components/ui/skeleton';
import { DisplayName } from '~/components/user/avatar';
import {
  removeSignupHistoryQueries,
  useSignupHistory,
  type SignupHistoryFilters,
} from '~/hooks/useEvent';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import type { UserRef } from '~/lib/userDisplayName';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';

import { SignupHistoryTable } from './SignupHistoryTable';

const log = getLogger('SignupHistorySection');

// Radix Select rejects '' as an item value.
const ALL = 'all';

export type HistoryMemberOption = { user_id: number; user: UserRef };

export type SignupHistorySectionProps = {
  eventId: number;
  isAdmin: boolean;
  eventTimezone?: string;
  /** Sheet layout: secondary columns fold into each row's meta line. */
  compact?: boolean;
} & (
  | { fixedUser: HistorySubject; memberOptions?: never }
  | { fixedUser?: undefined; memberOptions: HistoryMemberOption[] }
);

/** Staff-only view of an event's signup ledger, newest first, with server-side filters. */
export function SignupHistorySection({
  eventId,
  isAdmin,
  eventTimezone,
  compact = false,
  fixedUser,
  memberOptions,
}: SignupHistorySectionProps) {
  const queryClient = useQueryClient();
  const signedIn = useUserStore((s) => !!s.currentUser?.pk);
  const allowed = isAdmin && signedIn;

  const [member, setMember] = useState<number | undefined>();
  const [action, setAction] = useState<string | undefined>();

  const user = fixedUser ? (fixedUser.user_id ?? undefined) : member;
  const filters: SignupHistoryFilters = {
    ...(user !== undefined && { user }),
    ...(action !== undefined && { action }),
  };
  const enabled = allowed && (!fixedUser || fixedUser.user_id != null);
  const {
    data,
    error,
    isPending,
    isPlaceholderData,
    hasNextPage,
    isFetchingNextPage,
    isFetchNextPageError,
    fetchNextPage,
  } = useSignupHistory(eventId, filters, enabled);

  // A disabled query still returns its cached data: drop it when the viewer loses access.
  useEffect(() => {
    if (!allowed) removeSignupHistoryQueries(queryClient, eventId);
  }, [allowed, eventId, queryClient]);

  useEffect(() => {
    if (error) {
      log.error('signup_history_load_failed', {
        eventId,
        error,
        contract: error instanceof ZodError,
      });
    }
  }, [error, eventId]);

  const rows = useMemo(
    () => data?.pages.flatMap((p) => p.results) ?? [],
    [data],
  );
  // Placeholder data reports no next page; keep Load more visible (disabled) meanwhile.
  const showMore = isPlaceholderData ? !!data?.pages.at(-1)?.next : hasNextPage;
  const memberView = user !== undefined;
  const originalId =
    memberView && action === undefined && !hasNextPage && !isPlaceholderData
      ? originalSignupId(rows)
      : null;

  const members = useMemo(
    () =>
      (memberOptions ?? [])
        .map((o) => ({ value: String(o.user_id), label: DisplayName(o.user) }))
        .sort((a, b) => a.label.localeCompare(b.label)),
    [memberOptions],
  );

  if (!allowed) return null;

  const filtered = (!fixedUser && member !== undefined) || action !== undefined;
  // A failed Load more keeps the loaded rows; only a first-page failure replaces them.
  const loadError = error && !isFetchNextPageError ? error : null;
  const moreError = error && isFetchNextPageError ? error : null;
  const clearFilters = () => {
    setMember(undefined);
    setAction(undefined);
  };

  const emptyMessage = (
    <span data-testid="signup-history-empty">
      {action !== undefined
        ? 'No changes match these filters.'
        : memberView
          ? 'No changes recorded for this member. Sign-ups made before history tracking began have no entries.'
          : 'No changes recorded yet.'}
    </span>
  );

  return (
    <section
      className="flex flex-col gap-3"
      data-testid="signup-history-section"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        {!fixedUser && (
          <BrandSelect
            value={member === undefined ? ALL : String(member)}
            onValueChange={(v) => setMember(v === ALL ? undefined : Number(v))}
          >
            <BrandSelectTrigger
              className="min-h-11 w-full sm:w-56"
              aria-label="Filter by member"
              data-testid="signup-history-member-filter"
            >
              <SelectValue />
            </BrandSelectTrigger>
            <BrandSelectContent>
              <BrandSelectItem value={ALL}>All members</BrandSelectItem>
              {members.map((m) => (
                <BrandSelectItem key={m.value} value={m.value}>
                  {m.label}
                </BrandSelectItem>
              ))}
            </BrandSelectContent>
          </BrandSelect>
        )}
        <BrandSelect
          value={action ?? ALL}
          onValueChange={(v) => setAction(v === ALL ? undefined : v)}
        >
          <BrandSelectTrigger
            className="min-h-11 w-full sm:w-56"
            aria-label="Filter by action"
            data-testid="signup-history-action-filter"
          >
            <SelectValue />
          </BrandSelectTrigger>
          <BrandSelectContent>
            <BrandSelectItem value={ALL}>All actions</BrandSelectItem>
            {SIGNUP_LEDGER_ACTIONS.map((a) => (
              <BrandSelectItem key={a} value={a}>
                {SIGNUP_ACTION_LABELS[a]}
              </BrandSelectItem>
            ))}
          </BrandSelectContent>
        </BrandSelect>
        {filtered && (
          <SecondaryButton
            className="min-h-11"
            onClick={clearFilters}
            data-testid="signup-history-clear-filters"
          >
            Clear filters
          </SecondaryButton>
        )}
      </div>

      {loadError ? (
        <p className="text-sm text-error" data-testid="signup-history-error">
          {extractApiError(loadError) ?? 'Could not load sign-up history.'}
        </p>
      ) : isPending ? (
        <div
          className="flex flex-col gap-2"
          data-testid="signup-history-loading"
        >
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : (
        <div
          data-testid="signup-history-table"
          aria-busy={isPlaceholderData}
          className={cn(isPlaceholderData && 'opacity-60')}
        >
          <SignupHistoryTable
            rows={rows}
            compact={compact}
            eventTimezone={eventTimezone}
            originalId={originalId}
            emptyMessage={emptyMessage}
          />
        </div>
      )}

      {showMore && !loadError && (
        <div className="flex flex-col items-center gap-2 sm:flex-row sm:justify-center">
          {moreError && !isFetchingNextPage && (
            <p
              className="text-center text-sm text-error"
              role="alert"
              data-testid="signup-history-load-more-error"
            >
              {extractApiError(moreError) ?? 'Could not load more history.'}
            </p>
          )}
          <SecondaryButton
            className="min-h-11"
            onClick={() => void fetchNextPage()}
            disabled={isPlaceholderData || isFetchingNextPage}
            data-testid="signup-history-load-more"
          >
            {isFetchingNextPage
              ? 'Loading…'
              : moreError
                ? 'Retry'
                : 'Load more'}
          </SecondaryButton>
        </div>
      )}
    </section>
  );
}
