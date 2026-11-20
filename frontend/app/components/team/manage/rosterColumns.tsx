import type {
  ManagedTeam,
  RosterUser,
} from '~/components/api/teamManagementAPI';
import {
  DataTableColumnHeader,
  DataTableRowActions,
  type AppColumnDef,
  type AppRow,
  type DataTableRowAction,
} from '~/components/ui/data-table';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import type { PendingTeamAction } from './pendingTeamAction';
import { RosterStatusBadge } from './RosterStatusBadge';
import {
  clearDeputyRequest,
  markDropoutRequest,
  removeStandinRequest,
  restoreMemberRequest,
  setCaptainRequest,
  setDeputyRequest,
  subInRequest,
} from './teamActionCopy';

export type RosterListStatus = 'member' | 'standin' | 'dropout';

export interface RosterRow {
  user: RosterUser;
  status: RosterListStatus;
  isCaptain: boolean;
  isDeputy: boolean;
}

export type RosterColumnId = 'player' | 'role' | 'mmr' | 'actions';

export const DEFAULT_ROSTER_COLUMNS: readonly RosterColumnId[] = [
  'player',
  'role',
  'mmr',
  'actions',
];

export const LAST_MEMBER_HINT = 'A team needs at least one member';

const byName = (a: RosterUser, b: RosterUser): number =>
  DisplayName(a).localeCompare(DisplayName(b));

/** One row per user: members, then stand-ins, then dropouts, each by name. */
export function buildRosterRows(team: ManagedTeam): RosterRow[] {
  const row =
    (status: RosterListStatus) =>
    (user: RosterUser): RosterRow => ({
      user,
      status,
      isCaptain: user.pk === team.captain?.pk,
      isDeputy: user.pk === team.deputy_captain?.pk,
    });
  return [
    ...[...team.members].sort(byName).map(row('member')),
    ...[...team.dropin_members].sort(byName).map(row('standin')),
    ...[...team.left_members].sort(byName).map(row('dropout')),
  ];
}

const roleLabel = (r: RosterRow): string =>
  r.status === 'standin'
    ? 'Stand-in'
    : r.status === 'dropout'
      ? 'Dropout'
      : r.isCaptain
        ? 'Captain'
        : r.isDeputy
          ? 'Deputy'
          : 'Member';

const ROLE_RANK: Record<string, number> = {
  Captain: 0,
  Deputy: 1,
  Member: 2,
  'Stand-in': 3,
  Dropout: 4,
};

const byRole = (a: AppRow<RosterRow>, b: AppRow<RosterRow>): number =>
  ROLE_RANK[roleLabel(a.original)] - ROLE_RANK[roleLabel(b.original)];

const formatMmr = (mmr: number | null | undefined): string | null =>
  mmr == null ? null : `${mmr.toLocaleString('en-US')} MMR`;

export interface RosterActionContext {
  team: ManagedTeam;
  testIdPrefix: string;
  onRequestAction: (request: PendingTeamAction) => void;
}

/** The actions a staff member can take on one roster row. */
export function rosterRowActions(
  row: RosterRow,
  { team, testIdPrefix, onRequestAction }: RosterActionContext,
): DataTableRowAction[] {
  const { user, status } = row;
  const action = (
    key: string,
    label: string,
    request: () => PendingTeamAction,
    extra: Partial<DataTableRowAction> = {},
  ): DataTableRowAction => ({
    key,
    label,
    onSelect: () => onRequestAction(request()),
    testId: `${testIdPrefix}-${key}-${user.pk}`,
    ...extra,
  });

  if (status === 'standin') {
    return [
      action('sub-in', 'Sub in', () => subInRequest(team, user)),
      action(
        'remove-standin',
        'Remove stand-in',
        () => removeStandinRequest(team, user),
        { destructive: true },
      ),
    ];
  }
  if (status === 'dropout') {
    return [
      action('restore', 'Restore', () => restoreMemberRequest(team, user)),
    ];
  }

  const lastMember = team.members.length === 1;
  const actions: DataTableRowAction[] = [];
  if (!row.isCaptain) {
    actions.push(
      action('make-captain', 'Make captain', () =>
        setCaptainRequest(team, user),
      ),
    );
    actions.push(
      row.isDeputy
        ? action('clear-deputy', 'Clear deputy', () => clearDeputyRequest(team))
        : action('make-deputy', 'Make deputy', () =>
            setDeputyRequest(team, user),
          ),
    );
  }
  actions.push(
    action(
      'mark-dropout',
      'Mark dropout',
      () => markDropoutRequest(team, user),
      {
        destructive: true,
        disabled: lastMember,
        hint: lastMember ? LAST_MEMBER_HINT : undefined,
      },
    ),
  );
  return actions;
}

export interface MakeRosterColumnsOptions extends RosterActionContext {
  columns?: readonly RosterColumnId[];
  pending?: boolean;
}

/**
 * Column defs for RosterTable. Phones show the player (MMR stacked under the
 * name), role badges and the actions menu; the MMR column appears from `sm`.
 */
export function makeRosterColumns({
  team,
  testIdPrefix,
  onRequestAction,
  columns = DEFAULT_ROSTER_COLUMNS,
  pending = false,
}: MakeRosterColumnsOptions): AppColumnDef<RosterRow>[] {
  const ctx = { team, testIdPrefix, onRequestAction };
  const all: Record<RosterColumnId, AppColumnDef<RosterRow>> = {
    player: {
      id: 'player',
      accessorFn: (r) => DisplayName(r.user),
      sortFn: 'alphanumeric',
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Player" />
      ),
      cell: ({ row }) => {
        const { user } = row.original;
        const mmr = formatMmr(user.mmr);
        return (
          <div className="flex min-w-0 items-center gap-2">
            <UserAvatar user={user} size="sm" />
            <div className="flex min-w-0 flex-col">
              <span className="wrap-anywhere">{DisplayName(user)}</span>
              {mmr ? (
                <span
                  className="text-xs text-muted-foreground tabular-nums sm:hidden"
                  data-testid={`${testIdPrefix}-mmr-stacked-${user.pk}`}
                >
                  {mmr}
                </span>
              ) : null}
            </div>
          </div>
        );
      },
    },
    role: {
      id: 'role',
      accessorFn: roleLabel,
      sortFn: byRole,
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Role" />
      ),
      cell: ({ row }) => {
        const r = row.original;
        const badges = [
          r.isCaptain ? <RosterStatusBadge key="c" status="captain" /> : null,
          r.isDeputy ? <RosterStatusBadge key="d" status="deputy" /> : null,
          r.status === 'standin' ? (
            <RosterStatusBadge key="s" status="standin" />
          ) : null,
          r.status === 'dropout' ? (
            <RosterStatusBadge key="o" status="dropout" />
          ) : null,
        ].filter(Boolean);
        return badges.length ? (
          <div className="flex flex-wrap gap-1">{badges}</div>
        ) : (
          <span className="text-xs text-muted-foreground">Member</span>
        );
      },
      meta: { headClassName: 'w-24', cellClassName: 'w-24' },
    },
    mmr: {
      id: 'mmr',
      accessorFn: (r) => r.user.mmr ?? 0,
      enableSorting: false,
      header: 'MMR',
      cell: ({ row }) => row.original.user.mmr?.toLocaleString('en-US') ?? '—',
      meta: {
        headClassName: 'hidden w-20 text-right sm:table-cell',
        cellClassName:
          'hidden w-20 text-right tabular-nums text-muted-foreground sm:table-cell',
      },
    },
    actions: {
      id: 'actions',
      enableSorting: false,
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => (
        <DataTableRowActions
          label={`Actions for ${DisplayName(row.original.user)}`}
          actions={rosterRowActions(row.original, ctx)}
          disabled={pending}
          data-testid={`${testIdPrefix}-actions-${row.original.user.pk}`}
        />
      ),
      meta: {
        headClassName: 'w-14 sm:w-12',
        cellClassName: 'w-14 text-right sm:w-12',
      },
    },
  };
  return columns.map((id) => all[id]);
}
