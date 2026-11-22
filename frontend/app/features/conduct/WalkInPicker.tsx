import { useQuery } from '@tanstack/react-query';
import { useEffect, useId, useMemo, useState } from 'react';
import { searchUsers, type SearchUserResult } from '~/components/api/api';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { Input } from '~/components/ui/input';
import { Label } from '~/components/ui/label';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import { conductKeys, type OrgFeatureAccess } from '~/features/org-features';
import { useDebouncedValue } from '~/hooks/useDebouncedValue';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import type { WalkIn } from './attendanceDraft';

const log = getLogger('WalkInPicker');

const DEBOUNCE_MS = 300;
// backend/app/views/admin_team.py search_users rejects q under 3
export const WALK_IN_SEARCH_MIN = 3;

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
  eventId: number;
  access: OrgFeatureAccess;
  excludeUserPks: ReadonlySet<number>;
  onPick: (walkIn: WalkIn) => void;
}

export function WalkInPicker({
  open,
  onOpenChange,
  orgId,
  eventId,
  access,
  excludeUserPks,
  onPick,
}: WalkInPickerProps) {
  const [query, setQuery] = useState('');
  const term = useDebouncedValue(query.trim(), DEBOUNCE_MS);
  const inputId = useId();

  useEffect(() => {
    if (open) setQuery('');
  }, [open]);

  const search = useQuery({
    queryKey: [
      ...conductKeys.event(orgId, access.viewerPk, eventId),
      'walk-in-search',
      term,
    ],
    queryFn: () => searchUsers(term, orgId),
    enabled: open && term.length >= WALK_IN_SEARCH_MIN,
  });

  const typed = query.trim();
  const tooShort = typed.length < WALK_IN_SEARCH_MIN;
  const searching = !tooShort && (search.isFetching || typed !== term);

  useEffect(() => {
    if (search.isError)
      log.error('walk-in search failed', { orgId, error: search.error });
  }, [search.isError, search.error, orgId]);

  const candidates = useMemo<Candidate[]>(
    () =>
      (search.data ?? []).filter(
        (u): u is Candidate =>
          u.membership === 'org' && u.pk != null && !excludeUserPks.has(u.pk),
      ),
    [search.data, excludeUserPks],
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
        <div className="flex flex-col gap-2">
          <Label htmlFor={inputId}>Search org members</Label>
          <Input
            id={inputId}
            data-testid="attendance-walkin-search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Name or username"
            autoComplete="off"
          />
        </div>
        {tooShort ? (
          <p
            className="text-sm text-muted-foreground"
            data-testid="attendance-walkin-hint"
          >
            Type at least {WALK_IN_SEARCH_MIN} characters
          </p>
        ) : (
          <>
            <ul
              className="flex max-h-72 flex-col gap-1 overflow-y-auto"
              data-testid="attendance-walkin-results"
            >
              {candidates.map((user) => (
                <li key={user.pk}>
                  <SecondaryButton
                    className="min-h-11 w-full justify-start gap-2 sm:min-h-9"
                    data-testid={`attendance-walkin-option-${user.pk}`}
                    onClick={() => onPick(toWalkIn(user))}
                  >
                    <UserAvatar user={user} size="sm" />
                    <span className="min-w-0 break-words text-left">
                      {DisplayName(user)}
                    </span>
                  </SecondaryButton>
                </li>
              ))}
            </ul>
            {searching && (
              <p
                className="text-sm text-muted-foreground"
                data-testid="attendance-walkin-searching"
              >
                Searching...
              </p>
            )}
            {search.isError && !searching && (
              <p
                className="text-sm text-destructive"
                data-testid="attendance-walkin-error"
              >
                {extractApiError(search.error) ?? 'Search failed'}
              </p>
            )}
            {search.isSuccess && !searching && candidates.length === 0 && (
              <p
                className="text-sm text-muted-foreground"
                data-testid="attendance-walkin-empty"
              >
                No other org members match.
              </p>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
