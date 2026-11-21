// frontend/app/components/teamdraft/CompletedTeamDraftView.tsx
import { Trophy, Users } from 'lucide-react';
import { useCallback, useMemo, type ReactNode } from 'react';
import type { GameTypeValue } from '~/components/game/constants';
import { LeadershipProblemBadge } from '~/components/team/manage/LeadershipProblemBadge';
import {
  isUnresolvedLogUser,
  resolveLogUser,
} from '~/components/team/manage/resolveLogUser';
import {
  ROSTER_BADGE_SIZE,
  RosterStatusBadge,
  type RosterStatus,
} from '~/components/team/manage/RosterStatusBadge';
import type { TeamType } from '~/components/tournament/types';
import { Badge } from '~/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '~/components/ui/card';
import { useSharedPopoverActions } from '~/components/ui/shared-popover-context';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { UserStrip } from '~/components/user';
import { DisplayName } from '~/components/user/avatar';
import type { UserType } from '~/components/user/types';
import { UserAvatar } from '~/components/user/UserAvatar';
import { formatDuration } from '~/lib/dota/utils';
import { cn } from '~/lib/utils';
import { TeamPositionCoverageRow } from './TeamPositionCoverage';
import type { DraftRoundType } from './types';

interface CompletedTeamDraftViewProps {
  teams: TeamType[];
  gameType: GameTypeValue;
  organizationId?: number;
  leaguePk: number | null;
  rounds?: DraftRoundType[];
}

interface TeamCardProps {
  team: TeamType;
  rank: number;
  gameType: GameTypeValue;
  organizationId?: number;
  leaguePk: number | null;
  rounds?: DraftRoundType[];
  /** Shows leadership-problem flags; computed once by the caller. */
  canEdit?: boolean;
  /** Fallback for hydration's `{pk}` stubs. */
  tournamentUsers?: readonly UserType[] | null;
}

type ResolvedRosterUser =
  | { pk: number; user: UserType }
  | { pk: number; user: null; label: string };

function resolveRosterUser(
  user: UserType,
  tournamentUsers: readonly UserType[] | null | undefined,
): ResolvedRosterUser | null {
  if (user.pk == null) return null;
  const resolved = resolveLogUser(user.pk, {
    team: { members: [user] },
    tournamentUsers,
  });
  return isUnresolvedLogUser(resolved)
    ? { pk: user.pk, user: null, label: resolved.fallbackLabel }
    : { pk: user.pk, user: resolved as UserType };
}

function RosterBadges({ children }: { children: ReactNode }) {
  return <div className="flex items-center justify-end gap-1">{children}</div>;
}

function RosterExtraRow({
  entry,
  status,
  gameType,
  organizationId,
  leaguePk,
}: {
  entry: ResolvedRosterUser;
  status: Extract<RosterStatus, 'standin' | 'dropout'>;
  gameType: GameTypeValue;
  organizationId?: number;
  leaguePk: number | null;
}) {
  const testId = `team-card-${status}-${entry.pk}`;
  const badge = (
    <RosterBadges>
      <RosterStatusBadge status={status} />
    </RosterBadges>
  );
  const muted = status === 'dropout' && 'opacity-60';
  if (!entry.user) {
    return (
      <div
        data-testid={testId}
        className={cn(
          'flex items-center gap-2 rounded px-2 py-1 text-sm text-muted-foreground',
          muted,
        )}
      >
        <span className="flex-1 truncate">{entry.label}</span>
        {badge}
      </div>
    );
  }
  return (
    <UserStrip
      user={entry.user}
      compact
      showBorder={false}
      organizationId={organizationId}
      gameType={gameType}
      statsLeagueId={leaguePk}
      className={cn('bg-base-700/30 hover:bg-base-700/50', muted)}
      contextSlot={badge}
      data-testid={testId}
    />
  );
}

// Team Members List component
function TeamMembersList({
  members,
  captain,
  deputy,
  standins,
  dropouts,
  tournamentUsers,
  gameType,
  organizationId,
  leaguePk,
  rounds,
}: {
  members: UserType[];
  captain: UserType | null | undefined;
  deputy?: UserType | null;
  standins?: UserType[] | null;
  dropouts?: UserType[] | null;
  tournamentUsers?: readonly UserType[] | null;
  gameType: GameTypeValue;
  organizationId?: number;
  leaguePk: number | null;
  rounds?: DraftRoundType[];
}) {
  // Sort by MMR (highest first)
  const sortedMembers = useMemo(() => {
    return members
      .map((m) => resolveRosterUser(m, tournamentUsers)?.user ?? m)
      .sort((a, b) => (b.mmr || 0) - (a.mmr || 0));
  }, [members, tournamentUsers]);
  const resolveAll = (users: UserType[] | null | undefined) =>
    (users ?? [])
      .map((u) => resolveRosterUser(u, tournamentUsers))
      .filter((e): e is ResolvedRosterUser => e != null);
  const standinRows = resolveAll(standins);
  const dropoutRows = resolveAll(dropouts);

  return (
    <div className="space-y-1">
      {sortedMembers.map((member) => {
        const round = rounds?.find((r) => r.choice?.pk === member.pk);
        const isCaptain = captain?.pk === member.pk;
        const isDeputy = deputy?.pk != null && deputy.pk === member.pk;
        const hasDuration = typeof round?.pick_duration_ms === 'number';
        const hasSkips = (round?.skip_count ?? 0) > 0;
        return (
          <UserStrip
            key={member.pk}
            user={member}
            compact
            showBorder={false}
            organizationId={organizationId}
            gameType={gameType}
            statsLeagueId={leaguePk}
            className="bg-base-700/30 hover:bg-base-700/50"
            data-testid={`team-card-member-${member.pk}`}
            contextSlot={
              isCaptain || isDeputy || hasDuration || hasSkips ? (
                <RosterBadges>
                  {isCaptain && <RosterStatusBadge status="captain" />}
                  {isDeputy && <RosterStatusBadge status="deputy" />}
                  {hasDuration && (
                    <Badge
                      variant="outline"
                      className={ROSTER_BADGE_SIZE}
                      data-testid={`pick-duration-${member.pk}`}
                    >
                      {formatDuration(
                        (round!.pick_duration_ms as number) / 1000,
                      )}
                    </Badge>
                  )}
                  {hasSkips && (
                    <Badge
                      variant="outline"
                      className={cn(
                        ROSTER_BADGE_SIZE,
                        'text-warning border-warning/30',
                      )}
                      data-testid={`pick-skips-${member.pk}`}
                    >
                      skipped ×{round!.skip_count}
                    </Badge>
                  )}
                </RosterBadges>
              ) : undefined
            }
          />
        );
      })}
      {standinRows.map((entry) => (
        <RosterExtraRow
          key={`standin-${entry.pk}`}
          entry={entry}
          status="standin"
          gameType={gameType}
          organizationId={organizationId}
          leaguePk={leaguePk}
        />
      ))}
      {dropoutRows.map((entry) => (
        <RosterExtraRow
          key={`dropout-${entry.pk}`}
          entry={entry}
          status="dropout"
          gameType={gameType}
          organizationId={organizationId}
          leaguePk={leaguePk}
        />
      ))}
    </div>
  );
}

function TeamCard({
  team,
  rank,
  gameType,
  organizationId,
  leaguePk,
  rounds,
  canEdit = false,
  tournamentUsers,
}: TeamCardProps) {
  const { openTeamModal } = useSharedPopoverActions();
  const captain = team.captain;
  const displayName = captain ? DisplayName(captain) : team.name;

  // Calculate average MMR
  const averageMMR = useMemo(() => {
    if (!team.members || team.members.length === 0) return 0;
    const totalMMR = team.members.reduce(
      (acc: number, member: UserType) => acc + (member.mmr || 0),
      0,
    );
    return Math.round(totalMMR / team.members.length);
  }, [team.members]);

  // Determine rank badge color
  const rankColors = [
    'bg-medal-gold text-base-950', // 1st - Gold
    'bg-medal-silver text-base-950', // 2nd - Silver
    'bg-medal-bronze text-foreground', // 3rd - Bronze
  ];
  const rankColor = rankColors[rank - 1] || 'bg-base-50 text-foreground';

  const handleClick = useCallback(() => {
    openTeamModal(team);
  }, [team, openTeamModal]);

  return (
    <Card
      className={cn(
        'w-full cursor-pointer transition-all duration-200 flex flex-col',
        'hover:ring-2 hover:ring-primary/50 hover:shadow-lg',
        'bg-card/80 border-border',
      )}
      data-testid={`completed-team-card-${team.pk}`}
      onClick={handleClick}
    >
      <CardHeader className="pb-2 shrink-0">
        <div className="flex items-center gap-3">
          {/* Rank Badge */}
          <Badge className={cn('text-sm font-bold px-2 py-1', rankColor)}>
            #{rank}
          </Badge>

          {/* Captain Avatar */}
          <UserAvatar
            user={captain}
            size="xl"
            className="ring-2 ring-base-50"
          />

          {/* Team Name & Captain */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 min-w-0">
              <CardTitle
                className="text-lg text-white truncate"
                data-testid="team-card-name"
              >
                {team.name}
              </CardTitle>
              {canEdit && !!team.leadership_problems?.length && (
                <LeadershipProblemBadge
                  problems={team.leadership_problems}
                  team={team}
                />
              )}
            </div>
            <p className="text-sm text-muted-foreground truncate">
              Captain: {displayName}
            </p>
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-0 flex-1 flex flex-col min-h-0">
        {/* Stats Row */}
        <div className="flex items-center gap-4 mb-3 shrink-0">
          <div className="flex items-center gap-1.5">
            <Trophy className="h-4 w-4 text-medal-gold" />
            <span
              className="text-sm font-medium text-foreground"
              data-testid="team-avg-mmr-label"
            >
              {averageMMR.toLocaleString()} avg MMR
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <Users className="h-4 w-4 text-info" />
            <span className="text-sm text-text-secondary">
              {team.members?.length || 0} players
            </span>
          </div>
        </div>

        {/* Tabs for Members and Position Coverage - always visible */}
        {/* Stop propagation to prevent opening team modal when clicking tabs */}
        <div
          onClick={(e) => e.stopPropagation()}
          className="flex-1 flex flex-col min-h-0"
        >
          {/* Position coverage requires 2+ members to be meaningful */}
          {(team.members?.length || 0) >= 2 ? (
            <Tabs
              defaultValue="members"
              className="w-full flex-1 flex flex-col min-h-0"
            >
              <TabsList className="w-full grid grid-cols-2 h-8 mb-2 shrink-0">
                <TabsTrigger value="members" className="text-xs">
                  Members
                </TabsTrigger>
                <TabsTrigger value="positions" className="text-xs">
                  Guessed Positions
                </TabsTrigger>
              </TabsList>
              <TabsContent
                value="positions"
                className="mt-0 flex-1 overflow-y-auto"
              >
                <TeamPositionCoverageRow
                  team={team}
                  teamName={team.name || displayName}
                  showFullTable
                />
              </TabsContent>
              <TabsContent
                value="members"
                className="mt-0 flex-1 overflow-y-auto"
              >
                <TeamMembersList
                  members={team.members || []}
                  captain={captain}
                  deputy={team.deputy_captain}
                  standins={team.dropin_members}
                  dropouts={team.left_members}
                  tournamentUsers={tournamentUsers}
                  gameType={gameType}
                  organizationId={organizationId}
                  leaguePk={leaguePk}
                  rounds={rounds}
                />
              </TabsContent>
            </Tabs>
          ) : (
            <TeamMembersList
              members={team.members || []}
              captain={captain}
              deputy={team.deputy_captain}
              standins={team.dropin_members}
              dropouts={team.left_members}
              tournamentUsers={tournamentUsers}
              gameType={gameType}
              organizationId={organizationId}
              leaguePk={leaguePk}
              rounds={rounds}
            />
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// Export TeamCard and TeamMembersList for reuse in TeamsTab
export { TeamCard, TeamMembersList };

export function CompletedTeamDraftView({
  teams,
  gameType,
  organizationId,
  leaguePk,
  rounds,
}: CompletedTeamDraftViewProps) {
  // Sort teams by average MMR (highest first)
  const sortedTeams = useMemo(() => {
    return [...teams].sort((a, b) => {
      const aMMR =
        a.members?.reduce(
          (acc: number, m: UserType) => acc + (m.mmr || 0),
          0,
        ) || 0;
      const bMMR =
        b.members?.reduce(
          (acc: number, m: UserType) => acc + (m.mmr || 0),
          0,
        ) || 0;
      const aAvg = a.members?.length ? aMMR / a.members.length : 0;
      const bAvg = b.members?.length ? bMMR / b.members.length : 0;
      return bAvg - aAvg;
    });
  }, [teams]);

  if (!teams || teams.length === 0) {
    return (
      <div
        className="flex-1 flex items-center justify-center"
        data-testid="completed-team-draft-empty"
      >
        <p className="text-muted-foreground">No teams drafted yet</p>
      </div>
    );
  }

  return (
    <div
      className="flex-1 flex flex-col items-center p-4 md:p-8"
      data-testid="completed-team-draft-view"
    >
      <h2 className="text-2xl md:text-3xl font-bold text-white mb-6 md:mb-8">
        Team Draft Complete
      </h2>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 w-full max-w-6xl">
        {sortedTeams.map((team, index) => (
          <TeamCard
            key={team.pk}
            team={team}
            rank={index + 1}
            gameType={gameType}
            organizationId={organizationId}
            leaguePk={leaguePk}
            rounds={rounds}
          />
        ))}
      </div>
    </div>
  );
}
