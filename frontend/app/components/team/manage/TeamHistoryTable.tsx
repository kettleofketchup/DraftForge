import { format, formatDistanceToNow } from 'date-fns';
import { ChevronLeft, ChevronRight, TriangleAlert } from 'lucide-react';
import { useMemo } from 'react';
import { z } from 'zod';

import type {
  TeamHistoryPage,
  TeamLog,
} from '~/components/api/teamManagementAPI';
import { ordinal } from '~/components/team/teamStatus';
import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import { DataTable, type AppColumnDef } from '~/components/ui/data-table';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import type { UserLike } from './leadershipProblemText';
import { isUnresolvedLogUser, type UnresolvedLogUser } from './resolveLogUser';
import { teamLogActionLabel, teamLogViaLabel } from './teamLogLabels';

export type ResolveHistoryUser = (pk: number) => UserLike | UnresolvedLogUser;

export interface TeamHistoryTableProps {
  page: TeamHistoryPage | undefined;
  resolveUser: ResolveHistoryUser;
  onPrevious: () => void;
  onNext: () => void;
  loading?: boolean;
}

const SnapshotSchema = z.object({
  name: z.string().optional(),
  captain_id: z.number().nullable().optional(),
  deputy_captain_id: z.number().nullable().optional(),
  member_ids: z.array(z.number()).optional(),
  dropin_ids: z.array(z.number()).optional(),
  left_ids: z.array(z.number()).optional(),
  placement: z.number().nullable().optional(),
});
type Snapshot = z.infer<typeof SnapshotSchema>;

const ViolationsSchema = z.array(
  z.object({ code: z.string(), rule: z.string(), message: z.string() }),
);

const PERSON_FIELDS = [
  ['captain', 'captain_id'],
  ['deputy', 'deputy_captain_id'],
] as const;

const COUNT_FIELDS = [
  ['members', 'member_ids'],
  ['stand-ins', 'dropin_ids'],
  ['dropouts', 'left_ids'],
] as const;

const placementLabel = (placement: number | null): string =>
  placement == null ? 'in tournament' : ordinal(placement);

const userLabel = (user: UserLike | UnresolvedLogUser): string =>
  isUnresolvedLogUser(user) ? user.fallbackLabel : DisplayName(user);

/** "field: before -> after" lines for what differs between the log's snapshots. */
export function teamLogChanges(
  details: Record<string, unknown>,
  resolveUser: ResolveHistoryUser,
): string[] {
  const before = SnapshotSchema.safeParse(details.before);
  const after = SnapshotSchema.safeParse(details.after);
  if (!before.success || !after.success) return [];
  const a: Snapshot = before.data;
  const b: Snapshot = after.data;
  const person = (pk: number | null | undefined): string =>
    pk == null ? 'none' : userLabel(resolveUser(pk));
  const lines: string[] = [];
  if (a.name !== undefined && b.name !== undefined && a.name !== b.name) {
    lines.push(`name: ${a.name} -> ${b.name}`);
  }
  if (
    a.placement !== undefined &&
    b.placement !== undefined &&
    a.placement !== b.placement
  ) {
    lines.push(
      `placement: ${placementLabel(a.placement)} -> ${placementLabel(b.placement)}`,
    );
  }
  for (const [label, key] of PERSON_FIELDS) {
    if (key in a && key in b && a[key] !== b[key]) {
      lines.push(`${label}: ${person(a[key])} -> ${person(b[key])}`);
    }
  }
  for (const [label, key] of COUNT_FIELDS) {
    const from = a[key]?.length;
    const to = b[key]?.length;
    if (from !== undefined && to !== undefined && from !== to) {
      lines.push(`${label}: ${from} -> ${to}`);
    }
  }
  return lines;
}

type OverrideBadge = { label: string; message: string | null };

function overrideBadges(row: TeamLog): OverrideBadge[] {
  const violations = ViolationsSchema.safeParse(row.details.violations);
  if (violations.success && violations.data.length > 0) {
    return violations.data.map((v) => ({ label: v.rule, message: v.message }));
  }
  return row.override_rules
    .filter((code): code is string => typeof code === 'string')
    .map((code) => ({ label: code, message: null }));
}

function OverrideBadges({ row }: { row: TeamLog }) {
  const badges = overrideBadges(row);
  if (badges.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {badges.map((badge, i) => {
        const pill = (
          <Badge
            variant="secondary"
            tabIndex={badge.message ? 0 : undefined}
            aria-label={
              badge.message ? `${badge.label}: ${badge.message}` : badge.label
            }
            data-testid="team-history-override"
          >
            <TriangleAlert aria-hidden />
            {badge.label}
          </Badge>
        );
        return badge.message ? (
          <Tooltip key={`${badge.label}-${i}`}>
            <TooltipTrigger asChild>{pill}</TooltipTrigger>
            <TooltipContent>{badge.message}</TooltipContent>
          </Tooltip>
        ) : (
          <span key={`${badge.label}-${i}`}>{pill}</span>
        );
      })}
    </div>
  );
}

function Person({ user }: { user: TeamLog['actor'] }) {
  if (!user) return <span className="text-muted-foreground">System</span>;
  return (
    <span className="flex items-center gap-2">
      <UserAvatar user={user} size="sm" />
      <span>{DisplayName(user)}</span>
    </span>
  );
}

function makeColumns(resolveUser: ResolveHistoryUser): AppColumnDef<TeamLog>[] {
  return [
    {
      id: 'when',
      header: 'When',
      enableSorting: false,
      cell: ({ row }) => {
        const at = new Date(row.original.created_at);
        return (
          <time
            dateTime={row.original.created_at}
            title={format(at, 'PPpp')}
            className="text-muted-foreground"
            data-testid="team-history-when"
          >
            {formatDistanceToNow(at, { addSuffix: true })}
          </time>
        );
      },
    },
    {
      id: 'who',
      header: 'Who',
      enableSorting: false,
      cell: ({ row }) => <Person user={row.original.actor} />,
    },
    {
      id: 'via',
      header: 'Via',
      enableSorting: false,
      cell: ({ row }) => (
        <Badge variant="outline">{teamLogViaLabel(row.original.via)}</Badge>
      ),
    },
    {
      id: 'action',
      header: 'Action',
      enableSorting: false,
      cell: ({ row }) => teamLogActionLabel(row.original.action),
    },
    {
      id: 'player',
      header: 'Player',
      enableSorting: false,
      cell: ({ row }) =>
        row.original.target ? <Person user={row.original.target} /> : null,
    },
    {
      id: 'reason',
      header: 'Reason',
      enableSorting: false,
      meta: {
        cellClassName: 'min-w-48 max-w-xs whitespace-normal break-words',
      },
      cell: ({ row }) => row.original.reason,
    },
    {
      id: 'overrides',
      header: 'Overrides',
      enableSorting: false,
      cell: ({ row }) => <OverrideBadges row={row.original} />,
    },
    {
      id: 'change',
      header: 'Change',
      enableSorting: false,
      meta: { cellClassName: 'min-w-40 whitespace-normal break-words' },
      cell: ({ row }) => (
        <ul className="flex flex-col gap-0.5 text-sm">
          {teamLogChanges(row.original.details, resolveUser).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ),
    },
  ];
}

export const TEAM_HISTORY_PAGE_SIZE = 25;

/** One server page of team history; paging is driven by the page's next/previous links. */
export function TeamHistoryTable({
  page,
  resolveUser,
  onPrevious,
  onNext,
  loading = false,
}: TeamHistoryTableProps) {
  const columns = useMemo(() => makeColumns(resolveUser), [resolveUser]);
  if (!page) {
    return <p className="text-sm text-muted-foreground">Loading history…</p>;
  }
  return (
    <div className="flex flex-col gap-3">
      <DataTable
        columns={columns}
        data={page.results}
        getRowId={(row) => row.id}
        getRowTestId={() => 'team-history-row'}
        pageSize={TEAM_HISTORY_PAGE_SIZE}
        emptyMessage="No changes recorded yet."
        density="compact"
        scrollX
        scrollTestId="team-history-scroll"
        scrollLabel="Team history"
        data-testid="team-history-table"
      />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground">
          {page.count} {page.count === 1 ? 'change' : 'changes'}
        </p>
        <div className="flex items-center gap-2">
          <SecondaryButton
            size="sm"
            className="min-h-11 sm:min-h-8"
            onClick={onPrevious}
            disabled={loading || page.previous == null}
            data-testid="team-history-prev"
          >
            <ChevronLeft className="size-4" aria-hidden />
            Previous
          </SecondaryButton>
          <SecondaryButton
            size="sm"
            className="min-h-11 sm:min-h-8"
            onClick={onNext}
            disabled={loading || page.next == null}
            data-testid="team-history-next"
          >
            Next
            <ChevronRight className="size-4" aria-hidden />
          </SecondaryButton>
        </div>
      </div>
    </div>
  );
}
