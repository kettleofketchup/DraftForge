import { useEffect, useMemo, useState } from 'react';
import type { SearchUserResult } from '~/components/api/api';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { UserPicker } from '~/components/user/search';
import { useUserSearch } from '~/hooks/useUserSearch';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import type { WalkIn } from './attendanceDraft';

const log = getLogger('WalkInPicker');

type Candidate = SearchUserResult & { pk: number };

function toWalkIn(user: Candidate): WalkIn {
  return {
    user_pk: user.pk,
    username: user.username ?? '',
    nickname: user.nickname ?? null,
    avatarUrl: user.avatarUrl ?? null,
  };
}

export interface WalkInPickerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  orgId: number;
  excludeUserPks: ReadonlySet<number>;
  onPick: (walkIn: WalkIn) => void;
}

export function WalkInPicker({
  open,
  onOpenChange,
  orgId,
  excludeUserPks,
  onPick,
}: WalkInPickerProps) {
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (open) setQuery('');
  }, [open]);

  const search = useUserSearch(query, { orgId, enabled: open });

  useEffect(() => {
    if (search.status === 'error')
      log.error('walk-in search failed', { orgId, error: search.error });
  }, [search.status, search.error, orgId]);

  const candidates = useMemo<Candidate[]>(
    () =>
      search.results.filter(
        (u): u is Candidate =>
          u.membership === 'org' && u.pk != null && !excludeUserPks.has(u.pk),
      ),
    [search.results, excludeUserPks],
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="attendance-walkin-dialog">
        <DialogHeader>
          <DialogTitle>Add walk-in</DialogTitle>
          <DialogDescription>
            Record an org member who played without signing up. Walk-ins are
            shown in their history but never counted in the score.
          </DialogDescription>
        </DialogHeader>
        <UserPicker
          query={query}
          onQueryChange={setQuery}
          results={candidates}
          status={search.status}
          onSelect={(user) => onPick(toWalkIn(user))}
          placeholder="Search org members by name"
          ariaLabel="Search org members"
          emptyMessage="No other org members match."
          errorMessage={extractApiError(search.error) ?? 'Search failed'}
          className="rounded-md border"
          listClassName="max-h-72"
          testIds={{
            input: 'attendance-walkin-search',
            results: 'attendance-walkin-results',
            option: (user) => `attendance-walkin-option-${user.pk}`,
            hint: 'attendance-walkin-hint',
            searching: 'attendance-walkin-searching',
            empty: 'attendance-walkin-empty',
            error: 'attendance-walkin-error',
          }}
        />
      </DialogContent>
    </Dialog>
  );
}
