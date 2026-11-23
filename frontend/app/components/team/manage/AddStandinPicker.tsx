import { UserPlus } from 'lucide-react';
import { useMemo, useState } from 'react';

import {
  RosterUserSchema,
  type RosterUser,
} from '~/components/api/teamManagementAPI';
import type { SearchUserResult } from '~/components/api/userAPI';
import type { OrganizationType } from '~/components/organization/schemas';
import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import { UserPicker, type UserPickerGroup } from '~/components/user/search';
import { useIsOrganizationStaff } from '~/hooks/usePermissions';
import { useUserSearch } from '~/hooks/useUserSearch';

export interface AddStandinPickerProps {
  organization: OrganizationType | null | undefined;
  leaguePk: number | null | undefined;
  excludePks: number[];
  /** Rostered on another team in this tournament; the server refuses them. */
  otherTeamPks?: number[];
  disabled?: boolean;
  onPick: (user: RosterUser) => void;
}

type Candidate = RosterUser & {
  label: string | null;
  onOtherTeam: boolean;
};

function toCandidate(
  result: SearchUserResult,
  onOtherTeam: boolean,
): Candidate | null {
  const parsed = RosterUserSchema.safeParse(result);
  return parsed.success
    ? { ...parsed.data, label: result.membership_label ?? null, onOtherTeam }
    : null;
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
  const isOrgStaff =
    useIsOrganizationStaff(organization) && organization?.pk != null;
  const orgPk = isOrgStaff ? organization?.pk : undefined;
  const league = isOrgStaff ? (leaguePk ?? undefined) : undefined;

  const search = useUserSearch(query, {
    orgId: orgPk,
    leagueId: league,
    enabled: open,
  });

  const groups = useMemo<UserPickerGroup<Candidate>[]>(() => {
    const excluded = new Set(excludePks);
    const elsewhere = new Set(otherTeamPks);
    const inside: Candidate[] = [];
    const outside: Candidate[] = [];
    for (const result of search.results) {
      if (result.pk == null || excluded.has(result.pk)) continue;
      const candidate = toCandidate(result, elsewhere.has(result.pk));
      if (!candidate) continue;
      const isInside =
        !isOrgStaff ||
        result.membership === 'org' ||
        result.membership === 'league';
      (isInside ? inside : outside).push(candidate);
    }
    return [
      {
        heading: isOrgStaff ? 'In this organization' : undefined,
        users: inside,
      },
      { heading: 'Not in this organization', users: outside },
    ];
  }, [search.results, excludePks, otherTeamPks, isOrgStaff]);

  const handleOpenChange = (next: boolean) => {
    if (!next) setQuery('');
    setOpen(next);
  };

  const pick = ({ label: _label, onOtherTeam: _other, ...user }: Candidate) => {
    handleOpenChange(false);
    onPick(user);
  };

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <SecondaryButton size="sm" disabled={disabled}>
          <UserPlus />
          Add stand-in
        </SecondaryButton>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="end">
        <UserPicker
          query={query}
          onQueryChange={setQuery}
          groups={groups}
          status={search.status}
          onSelect={pick}
          isDisabled={(user) => user.onOtherTeam}
          renderBadge={(user) =>
            user.onOtherTeam ? (
              <Badge variant="outline" className="text-xs">
                On another team
              </Badge>
            ) : isOrgStaff && user.label ? (
              <Badge variant="outline" className="text-xs">
                {user.label}
              </Badge>
            ) : null
          }
          errorMessage="Search unavailable"
          testIds={{
            input: 'team-standin-search',
            option: (user) => `team-standin-result-${user.pk}`,
          }}
          footer={
            isOrgStaff ? null : (
              <p className="border-t px-3 py-2 text-xs text-muted-foreground">
                {organization?.pk == null
                  ? 'This tournament has no organization to rank by.'
                  : "Organization membership can't be shown for your role."}
              </p>
            )
          }
        />
      </PopoverContent>
    </Popover>
  );
}
