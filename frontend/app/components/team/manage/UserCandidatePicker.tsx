import { useQuery } from '@tanstack/react-query';
import { Crown, UserPlus } from 'lucide-react';
import { useMemo, useState, type ReactNode } from 'react';

import {
  RosterUserSchema,
  type OtherTeamSummary,
  type RosterUser,
} from '~/components/api/teamManagementAPI';
import { searchUsers } from '~/components/api/userAPI';
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
import { cn } from '~/lib/utils';
import {
  candidateLabels,
  freePlayers,
  matchesQuery,
  type TeamCandidateRow,
} from './candidateStatus';
import { ROSTER_BADGE_SIZE, RosterStatusBadge } from './RosterStatusBadge';

const MIN_QUERY_LENGTH = 3;
const DEBOUNCE_MS = 300;

export type CandidatePickerMode = 'standin' | 'captain';

export interface UserCandidatePickerProps {
  mode: CandidatePickerMode;
  testIdPrefix: 'team-standin' | 'team-captain';
  organization: OrganizationType | null | undefined;
  leaguePk: number | null | undefined;
  excludePks: number[];
  /** Rostered on another live team in this tournament; the server refuses them. */
  otherTeamPks?: number[];
  otherTeams?: OtherTeamSummary[];
  teamRows?: TeamCandidateRow[];
  tournamentUsers?: RosterUser[];
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  triggerTestId?: string;
  disabled?: boolean;
  onPick: (user: RosterUser) => void;
}

type Candidate = {
  user: RosterUser;
  label: string | null;
  disabled: boolean;
};

const TRIGGER = {
  standin: {
    icon: UserPlus,
    text: 'Add stand-in',
    placeholder: 'Search users…',
  },
  captain: {
    icon: Crown,
    text: 'Replace captain',
    placeholder: 'Search players…',
  },
} as const;

function Status({ children }: { children: string }) {
  return (
    <p className="px-3 py-4 text-center text-sm text-muted-foreground">
      {children}
    </p>
  );
}

function LabelBadge({ children }: { children: string }) {
  return (
    <Badge variant="outline" className="ml-auto text-xs">
      {children}
    </Badge>
  );
}

export function UserCandidatePicker({
  mode,
  testIdPrefix,
  organization,
  leaguePk,
  excludePks,
  otherTeamPks,
  otherTeams,
  teamRows,
  tournamentUsers,
  open: openProp,
  onOpenChange,
  triggerTestId,
  disabled,
  onPick,
}: UserCandidatePickerProps) {
  const [innerOpen, setInnerOpen] = useState(false);
  const open = openProp ?? innerOpen;
  const [query, setQuery] = useState('');
  const trimmed = query.trim();
  const term = useDebouncedValue(trimmed, DEBOUNCE_MS);
  const isOrgStaff =
    useIsOrganizationStaff(organization) && organization?.pk != null;
  const orgPk = isOrgStaff ? organization?.pk : undefined;
  const league = isOrgStaff ? (leaguePk ?? undefined) : undefined;

  const search = useQuery({
    queryKey: ['userSearch', mode, term, orgPk ?? null, league ?? null],
    queryFn: () => searchUsers(term, orgPk, league),
    enabled: open && term.length >= MIN_QUERY_LENGTH,
  });

  const labels = useMemo(
    () => candidateLabels(otherTeams ?? [], otherTeamPks ?? []),
    [otherTeams, otherTeamPks],
  );

  const status = (pk: number) => labels.get(pk);

  const teamGroup = useMemo(
    () => (teamRows ?? []).filter((row) => matchesQuery(row.user, trimmed)),
    [teamRows, trimmed],
  );

  const freeGroup = useMemo(
    () =>
      mode === 'captain'
        ? freePlayers(
            otherTeams ?? [],
            labels,
            excludePks,
            tournamentUsers ?? [],
          ).filter((user) => matchesQuery(user, trimmed))
        : [],
    [mode, otherTeams, labels, excludePks, tournamentUsers, trimmed],
  );

  const { inside, outside } = useMemo(() => {
    const skip = new Set([
      ...excludePks,
      ...teamGroup.map((row) => row.user.pk),
      ...freeGroup.map((user) => user.pk),
    ]);
    const inside: Candidate[] = [];
    const outside: Candidate[] = [];
    for (const result of search.data ?? []) {
      if (result.pk == null || skip.has(result.pk)) continue;
      const parsed = RosterUserSchema.safeParse(result);
      if (!parsed.success) continue;
      const known = labels.get(result.pk);
      const candidate: Candidate = {
        user: parsed.data,
        label:
          known?.label ??
          (isOrgStaff ? (result.membership_label ?? null) : null),
        disabled: known?.disabled ?? false,
      };
      const isInside =
        !isOrgStaff ||
        result.membership === 'org' ||
        result.membership === 'league';
      (isInside ? inside : outside).push(candidate);
    }
    return { inside, outside };
  }, [search.data, excludePks, teamGroup, freeGroup, labels, isOrgStaff]);

  const handleOpenChange = (next: boolean) => {
    if (!next) setQuery('');
    setInnerOpen(next);
    onOpenChange?.(next);
  };

  const pick = (user: RosterUser) => {
    handleOpenChange(false);
    onPick(user);
  };

  const renderSearchItem = ({ user, label, disabled: off }: Candidate) => (
    <CommandItem
      key={user.pk}
      value={String(user.pk)}
      data-testid={`${testIdPrefix}-result-${user.pk}`}
      disabled={off}
      onSelect={() => pick(user)}
    >
      <UserAvatar user={user} size="sm" />
      <span className="truncate">{DisplayName(user)}</span>
      {label ? <LabelBadge>{label}</LabelBadge> : null}
    </CommandItem>
  );

  const renderTeamItem = ({ user, status: rowStatus }: TeamCandidateRow) => {
    const elsewhere = status(user.pk);
    const off = elsewhere?.disabled ?? false;
    return (
      <CommandItem
        key={user.pk}
        value={String(user.pk)}
        data-testid={`${testIdPrefix}-team-row-${user.pk}`}
        disabled={off}
        onSelect={() => pick(user)}
      >
        <UserAvatar user={user} size="sm" />
        <span className="truncate">{DisplayName(user)}</span>
        <span className="ml-auto flex shrink-0 items-center gap-1">
          {off && elsewhere ? <LabelBadge>{elsewhere.label}</LabelBadge> : null}
          {rowStatus === 'member' ? (
            <Badge
              variant="outline"
              className={cn(ROSTER_BADGE_SIZE, 'text-muted-foreground')}
            >
              Member
            </Badge>
          ) : (
            <RosterStatusBadge status={rowStatus} />
          )}
        </span>
      </CommandItem>
    );
  };

  const renderFreeItem = (user: RosterUser) => {
    const label = status(user.pk)?.label;
    return (
      <CommandItem
        key={user.pk}
        value={String(user.pk)}
        data-testid={`${testIdPrefix}-free-row-${user.pk}`}
        onSelect={() => pick(user)}
      >
        <UserAvatar user={user} size="sm" />
        <span className="truncate">{DisplayName(user)}</span>
        {label ? <LabelBadge>{label}</LabelBadge> : null}
      </CommandItem>
    );
  };

  const clientCount = teamGroup.length + freeGroup.length;
  const ready = trimmed.length >= MIN_QUERY_LENGTH;
  const settled = ready && term === trimmed;
  let searchBody: ReactNode = null;
  if (!ready) {
    searchBody = <Status>Type at least 3 characters to search.</Status>;
  } else if (search.isError) {
    searchBody = <Status>Search unavailable</Status>;
  } else if (!settled || search.isPending) {
    searchBody = <Status>Searching…</Status>;
  } else if (inside.length + outside.length === 0) {
    searchBody = clientCount ? null : <Status>No users found</Status>;
  } else {
    searchBody = (
      <>
        {inside.length ? (
          <CommandGroup
            heading={isOrgStaff ? 'In this organization' : undefined}
          >
            {inside.map(renderSearchItem)}
          </CommandGroup>
        ) : null}
        {outside.length ? (
          <CommandGroup heading="Not in this organization">
            {outside.map(renderSearchItem)}
          </CommandGroup>
        ) : null}
      </>
    );
  }

  const trigger = TRIGGER[mode];
  const TriggerIcon = trigger.icon;

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <SecondaryButton
          size="sm"
          disabled={disabled}
          data-testid={triggerTestId}
        >
          <TriggerIcon />
          {trigger.text}
        </SecondaryButton>
      </PopoverTrigger>
      <PopoverContent
        className="w-80 p-0"
        align="end"
        onFocusOutside={
          openProp === undefined ? undefined : (e) => e.preventDefault()
        }
      >
        <Command shouldFilter={false}>
          <CommandInput
            value={query}
            onValueChange={setQuery}
            placeholder={trigger.placeholder}
            aria-label="Search users"
            data-testid={`${testIdPrefix}-search`}
          />
          <CommandList>
            {teamGroup.length ? (
              <CommandGroup heading="This team">
                {teamGroup.map(renderTeamItem)}
              </CommandGroup>
            ) : null}
            {freeGroup.length ? (
              <CommandGroup heading="Free players (eliminated teams)">
                {freeGroup.map(renderFreeItem)}
              </CommandGroup>
            ) : null}
            {searchBody}
          </CommandList>
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
