import { Lock } from 'lucide-react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '~/components/ui/table';
import { UserAvatar } from '~/components/user/UserAvatar';
import { cn } from '~/lib/utils';
import type { LeaderboardResponse, LeaderboardRow } from './schemas';

export interface LeaderboardProps {
  data: LeaderboardResponse;
  viewerPk: number | null;
  membersPrivate: boolean;
  onSelectMember: (orgUserPk: number) => void;
}

function displayName(row: LeaderboardRow): string {
  return row.nickname || row.username;
}

function HiddenRowsNote({
  membersPrivate,
  signedIn,
  hasOwnRow,
}: {
  membersPrivate: boolean;
  signedIn: boolean;
  hasOwnRow: boolean;
}) {
  const className = 'flex items-center gap-2 text-sm text-muted-foreground';
  if (membersPrivate) {
    return (
      <p className={className} data-testid="contributions-members-private">
        <Lock className="h-4 w-4" />
        {hasOwnRow
          ? 'Members are private in this organization, so only your own standing is shown.'
          : 'Members are private in this organization.'}
      </p>
    );
  }
  if (!signedIn) {
    return (
      <p className={className} data-testid="contributions-members-signin">
        <Lock className="h-4 w-4" />
        Sign in as a member to see the leaderboard.
      </p>
    );
  }
  return (
    <p className={className} data-testid="contributions-members-only">
      <Lock className="h-4 w-4" />
      Only members of this organization can see the leaderboard.
    </p>
  );
}

export function Leaderboard({ data, viewerPk, membersPrivate, onSelectMember }: LeaderboardProps) {
  const rows = data.rows_visible ? data.rows : data.own_row ? [data.own_row] : [];
  const ownPk = data.own_row?.org_user_pk ?? null;
  const isOwn = (row: LeaderboardRow): boolean =>
    row.org_user_pk === ownPk || (viewerPk != null && row.user_pk === viewerPk);

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-lg border border-border bg-base-300/40 p-4">
        <div className="text-sm text-muted-foreground">Organization total</div>
        <div className="text-3xl font-bold tabular-nums" data-testid="contributions-org-total">
          {data.total.toLocaleString('en-US')}
          <span className="ml-1.5 text-base font-normal text-muted-foreground">points</span>
        </div>
      </div>

      {!data.rows_visible && (
        <HiddenRowsNote
          membersPrivate={membersPrivate}
          signedIn={viewerPk != null}
          hasOwnRow={data.own_row != null}
        />
      )}

      {rows.length === 0 ? (
        data.rows_visible && (
            <div className="py-6 text-center text-muted-foreground" data-testid="contributions-empty">
            No contributions in this period
          </div>
        )
      ) : (
        <Table>
          <TableHeader>
            <TableRow className="border-border">
              {data.rows_visible && <TableHead className="w-12">#</TableHead>}
              <TableHead>Member</TableHead>
              <TableHead className="text-right">Points</TableHead>
              <TableHead className="hidden text-right sm:table-cell">Entries</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, index) => {
              const own = isOwn(row);
              return (
                <TableRow
                  key={row.org_user_pk}
                  className={cn(
                    'cursor-pointer border-border hover:bg-base-300/60',
                    own && 'bg-primary/10 ring-1 ring-inset ring-primary/40',
                  )}
                  data-testid={`contributions-row-${row.org_user_pk}`}
                  data-own={own ? 'true' : 'false'}
                  aria-current={own ? 'true' : undefined}
                  tabIndex={0}
                  onClick={() => onSelectMember(row.org_user_pk)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onSelectMember(row.org_user_pk);
                    }
                  }}
                >
                  {data.rows_visible && (
                    <TableCell className="font-medium text-muted-foreground">{index + 1}</TableCell>
                  )}
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <UserAvatar
                        user={{
                          pk: row.user_pk,
                          username: row.username,
                          nickname: row.nickname,
                          avatarUrl: row.avatarUrl,
                        }}
                        size="sm"
                      />
                      <span className="font-medium">{displayName(row)}</span>
                      {own && <span className="text-xs text-primary">(you)</span>}
                    </div>
                  </TableCell>
                  <TableCell className="text-right font-semibold tabular-nums">
                    {row.points.toLocaleString('en-US')}
                  </TableCell>
                  <TableCell className="hidden text-right tabular-nums text-muted-foreground sm:table-cell">
                    {row.entries}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
