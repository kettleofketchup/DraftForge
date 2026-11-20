import { useQuery } from '@tanstack/react-query';
import { UserPlus } from 'lucide-react';
import { useMemo, useState, type ReactNode } from 'react';

import {
  RosterUserSchema,
  type RosterUser,
} from '~/components/api/teamManagementAPI';
import { searchUsers, type SearchUserResult } from '~/components/api/userAPI';
import type { OrganizationType } from '~/components/organization/schemas';
import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  Command,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '~/components/ui/command';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import { useDebouncedValue } from '~/hooks/useDebouncedValue';
import { useIsOrganizationStaff } from '~/hooks/usePermissions';

const MIN_QUERY_LENGTH = 3;
const DEBOUNCE_MS = 300;

export interface AddStandinPickerProps {
  organization: OrganizationType | null | undefined;
  leaguePk: number | null | undefined;
  excludePks: number[];
  /** Rostered on another team in this tournament; the server refuses them. */
  otherTeamPks?: number[];
  disabled?: boolean;
  onPick: (user: RosterUser) => void;
}

type Candidate = {
  user: RosterUser;
  label: string | null;
  onOtherTeam: boolean;
};

function toCandidate(
  result: SearchUserResult,
  onOtherTeam: boolean,
): Candidate | null {
  const parsed = RosterUserSchema.safeParse(result);
  return parsed.success
    ? {
        user: parsed.data,
        label: result.membership_label ?? null,
        onOtherTeam,
      }
    : null;
}

function Status({ children }: { children: string }) {
  return (
    <p className="px-3 py-4 text-center text-sm text-muted-foreground">
      {children}
    </p>
  );
}

export function AddStandinPicker({
  organization,
  leaguePk,
  excludePks,
  otherTeamPks,
  disabled,
  onPick,
}: AddStandinPickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const term = useDebouncedValue(query.trim(), DEBOUNCE_MS);
  const isOrgStaff =
    useIsOrganizationStaff(organization) && organization?.pk != null;
  const orgPk = isOrgStaff ? organization?.pk : undefined;
  const league = isOrgStaff ? (leaguePk ?? undefined) : undefined;

  const search = useQuery({
    queryKey: ['userSearch', 'standin', term, orgPk ?? null, league ?? null],
    queryFn: () => searchUsers(term, orgPk, league),
    enabled: open && term.length >= MIN_QUERY_LENGTH,
  });

  const { inside, outside } = useMemo(() => {
    const excluded = new Set(excludePks);
    const elsewhere = new Set(otherTeamPks);
    const inside: Candidate[] = [];
    const outside: Candidate[] = [];
    for (const result of search.data ?? []) {
      if (result.pk == null || excluded.has(result.pk)) continue;
      const candidate = toCandidate(result, elsewhere.has(result.pk));
      if (!candidate) continue;
      const isInside =
        !isOrgStaff ||
        result.membership === 'org' ||
        result.membership === 'league';
      (isInside ? inside : outside).push(candidate);
    }
    return { inside, outside };
  }, [search.data, excludePks, otherTeamPks, isOrgStaff]);

  const handleOpenChange = (next: boolean) => {
    if (!next) setQuery('');
    setOpen(next);
  };

  const pick = (user: RosterUser) => {
    handleOpenChange(false);
    onPick(user);
  };

  const renderItem = ({ user, label, onOtherTeam }: Candidate) => (
    <CommandItem
      key={user.pk}
      value={String(user.pk)}
      data-testid={`team-standin-result-${user.pk}`}
      disabled={onOtherTeam}
      onSelect={() => pick(user)}
    >
      <UserAvatar user={user} size="sm" />
      <span className="truncate">{DisplayName(user)}</span>
      {onOtherTeam ? (
        <Badge variant="outline" className="ml-auto text-xs">
          On another team
        </Badge>
      ) : isOrgStaff && label ? (
        <Badge variant="outline" className="ml-auto text-xs">
          {label}
        </Badge>
      ) : null}
    </CommandItem>
  );

  const ready = query.trim().length >= MIN_QUERY_LENGTH;
  const settled = ready && term === query.trim();
  let body: ReactNode;
  if (!ready) {
    body = <Status>Type at least 3 characters to search.</Status>;
  } else if (search.isError) {
    body = <Status>Search unavailable</Status>;
  } else if (!settled || search.isPending) {
    body = <Status>Searching…</Status>;
  } else if (inside.length + outside.length === 0) {
    body = <Status>No users found</Status>;
  } else {
    body = (
      <>
        {inside.length ? (
          <CommandGroup
            heading={isOrgStaff ? 'In this organization' : undefined}
          >
            {inside.map(renderItem)}
          </CommandGroup>
        ) : null}
        {outside.length ? (
          <CommandGroup heading="Not in this organization">
            {outside.map(renderItem)}
          </CommandGroup>
        ) : null}
      </>
    );
  }

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <SecondaryButton size="sm" disabled={disabled}>
          <UserPlus />
          Add stand-in
        </SecondaryButton>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="end">
        <Command shouldFilter={false}>
          <CommandInput
            value={query}
            onValueChange={setQuery}
            placeholder="Search users…"
            aria-label="Search users"
            data-testid="team-standin-search"
          />
          <CommandList>{body}</CommandList>
          {isOrgStaff ? null : (
            <p className="border-t px-3 py-2 text-xs text-muted-foreground">
              {organization?.pk == null
                ? 'This tournament has no organization to rank by.'
                : "Organization membership can't be shown for your role."}
            </p>
          )}
        </Command>
      </PopoverContent>
    </Popover>
  );
}
