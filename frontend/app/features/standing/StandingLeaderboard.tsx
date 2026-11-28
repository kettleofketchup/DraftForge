import { Lock } from 'lucide-react';
import { useMemo, type HTMLAttributes, type KeyboardEvent } from 'react';
import { DataTable } from '~/components/ui/data-table';
import { DisplayName } from '~/components/user/avatar';
import { cn } from '~/lib/utils';
import { FEEDBACK_PRIVATE_NOTE, formatTotal } from './format';
import type { StandingLeaderboard as StandingLeaderboardData } from './schemas';
import {
  makeStandingLeaderboardColumns,
  toStandingTableRows,
  type StandingTableRow,
} from './standingLeaderboardColumns';

const LEADERBOARD_PAGE_SIZE = 100;
const OWN_ROW_CLASS = 'bg-primary/10 ring-1 ring-inset ring-primary/40';

export interface StandingLeaderboardProps {
  board: StandingLeaderboardData;
  testIdPrefix: string;
  sampleLabel: string | null;
  totalUnit: string | null;
  emptyLabel: string;
  boardOpen: boolean;
  viewerPk: number | null;
  membersPrivate: boolean;
  canOpen: (row: StandingTableRow) => boolean;
  onOpen: (row: StandingTableRow) => void;
}

function HiddenRowsNote({
  testIdPrefix,
  membersPrivate,
  signedIn,
  hasOwnRow,
}: {
  testIdPrefix: string;
  membersPrivate: boolean;
  signedIn: boolean;
  hasOwnRow: boolean;
}) {
  const className = 'flex items-center gap-2 text-sm text-muted-foreground';
  if (membersPrivate) {
    return (
      <p className={className} data-testid={`${testIdPrefix}-members-private`}>
        <Lock className="h-4 w-4" />
        {hasOwnRow
          ? 'Members are private in this organization, so only your own standing is shown.'
          : 'Members are private in this organization.'}
      </p>
    );
  }
  if (!signedIn) {
    return (
      <p className={className} data-testid={`${testIdPrefix}-members-signin`}>
        <Lock className="h-4 w-4" />
        Sign in as a member to see the leaderboard.
      </p>
    );
  }
  return (
    <p className={className} data-testid={`${testIdPrefix}-members-only`}>
      <Lock className="h-4 w-4" />
      Only members of this organization can see the leaderboard.
    </p>
  );
}

export function StandingLeaderboard({
  board,
  testIdPrefix,
  sampleLabel,
  totalUnit,
  emptyLabel,
  boardOpen,
  viewerPk,
  membersPrivate,
  canOpen,
  onOpen,
}: StandingLeaderboardProps) {
  const rows = useMemo(
    () => toStandingTableRows(board, viewerPk),
    [board, viewerPk],
  );
  const columns = useMemo(
    () =>
      makeStandingLeaderboardColumns({
        testIdPrefix,
        metric: board.metric,
        sampleLabel,
        showRank: board.rows_visible,
      }),
    [testIdPrefix, board.metric, sampleLabel, board.rows_visible],
  );

  const getRowProps = (
    row: StandingTableRow,
  ): HTMLAttributes<HTMLTableRowElement> & { 'data-own': string } => {
    const base = {
      'data-own': row.own ? 'true' : 'false',
      'aria-current': row.own ? ('true' as const) : undefined,
      className: cn(row.own && OWN_ROW_CLASS),
    };
    if (!canOpen(row)) return base;
    return {
      ...base,
      className: cn('cursor-pointer hover:bg-base-300/60', base.className),
      role: 'button',
      tabIndex: 0,
      'aria-label': `Open ${DisplayName(row.member)}'s details`,
      onClick: () => onOpen(row),
      onKeyDown: (e: KeyboardEvent<HTMLTableRowElement>) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onOpen(row);
        }
      },
    };
  };

  return (
    <div className="flex flex-col gap-4">
      {board.total !== null && (
        <div className="rounded-lg border border-border bg-base-300/40 p-4">
          <div className="text-sm text-muted-foreground">
            Organization total
          </div>
          <div
            className="text-3xl font-bold tabular-nums"
            data-testid={`${testIdPrefix}-org-total`}
          >
            {formatTotal(board.total, 'int')}
            {totalUnit && (
              <span className="ml-1.5 text-base font-normal text-muted-foreground">
                {totalUnit}
              </span>
            )}
          </div>
        </div>
      )}

      {board.own_private && (
        <p
          className="flex items-center gap-2 text-sm text-muted-foreground"
          data-testid="standing-own-private"
        >
          <Lock className="size-4" aria-hidden="true" />
          {FEEDBACK_PRIVATE_NOTE}
        </p>
      )}

      {boardOpen && !board.rows_visible && (
        <HiddenRowsNote
          testIdPrefix={testIdPrefix}
          membersPrivate={membersPrivate}
          signedIn={viewerPk != null}
          hasOwnRow={board.own_row != null && !board.own_private}
        />
      )}

      {rows.length === 0 ? (
        board.rows_visible && (
          <div
            className="py-6 text-center text-muted-foreground"
            data-testid={`${testIdPrefix}-empty`}
          >
            {emptyLabel}
          </div>
        )
      ) : (
        <DataTable
          columns={columns}
          data={rows}
          getRowId={(r) => String(r.member.org_user_pk)}
          getRowTestId={(r) => `${testIdPrefix}-row-${r.member.org_user_pk}`}
          getRowProps={getRowProps}
          pageSize={LEADERBOARD_PAGE_SIZE}
          data-testid={`${testIdPrefix}-table`}
        />
      )}
    </div>
  );
}
