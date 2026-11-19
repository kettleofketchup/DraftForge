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
import { UserAvatar } from '~/components/user/UserAvatar';
import { DisplayName } from '~/components/user/avatar';
import { conductKeys, type OrgFeatureAccess } from '~/features/org-features';
import { useDebouncedValue } from '~/hooks/useDebouncedValue';

const DEBOUNCE_MS = 300;
const MIN_QUERY_LENGTH = 2;

export type WalkInCandidate = SearchUserResult & { pk: number };

export interface WalkInPickerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  orgId: number;
  access: OrgFeatureAccess;
  /** User pks already on the attendance list (rows and pending walk-ins). */
  excludeUserPks: ReadonlySet<number>;
  onPick: (user: WalkInCandidate) => void;
}

export function WalkInPicker({
  open,
  onOpenChange,
  orgId,
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
      ...conductKeys.all(orgId, access.viewerPk),
      'walk-in-search',
      term,
    ],
    queryFn: () => searchUsers(term, orgId),
    enabled: open && term.length >= MIN_QUERY_LENGTH,
  });

  const candidates = useMemo<WalkInCandidate[]>(
    () =>
      (search.data ?? []).filter(
        (u): u is WalkInCandidate =>
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
        <ul
          className="flex max-h-72 flex-col gap-1 overflow-y-auto"
          data-testid="attendance-walkin-results"
        >
          {candidates.map((user) => (
            <li key={user.pk}>
              <SecondaryButton
                className="min-h-11 w-full justify-start gap-2"
                data-testid={`attendance-walkin-option-${user.pk}`}
                onClick={() => onPick(user)}
              >
                <UserAvatar user={user} size="sm" />
                <span className="truncate">{DisplayName(user)}</span>
              </SecondaryButton>
            </li>
          ))}
        </ul>
        {term.length >= MIN_QUERY_LENGTH &&
          search.isSuccess &&
          candidates.length === 0 && (
            <p
              className="text-sm text-muted-foreground"
              data-testid="attendance-walkin-empty"
            >
              No other org members match.
            </p>
          )}
      </DialogContent>
    </Dialog>
  );
}
