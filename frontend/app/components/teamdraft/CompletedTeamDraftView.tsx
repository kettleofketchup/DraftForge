// frontend/app/components/teamdraft/CompletedTeamDraftView.tsx
import { useCallback, useMemo } from 'react';
import { Trophy, Users } from 'lucide-react';
import { Badge } from '~/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '~/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { useSharedPopoverActions } from '~/components/ui/shared-popover-context';
import { cn } from '~/lib/utils';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import { UserStrip } from '~/components/user';
import { TeamPositionCoverageRow } from './TeamPositionCoverage';
import { formatDuration } from '~/lib/dota/utils';
import type { DraftRoundType } from './types';
import type { TeamType } from '~/components/tournament/types';
import type { UserType } from '~/components/user/types';

interface CompletedTeamDraftViewProps {
  teams: TeamType[];
  organizationId?: number;
  leaguePk: number | null;
  rounds?: DraftRoundType[];
}

interface TeamCardProps {
  team: TeamType;
  rank: number;
  organizationId?: number;
  leaguePk: number | null;
  rounds?: DraftRoundType[];
}

// Team Members List component
function TeamMembersList({
  members,
  captain,
  organizationId,
  leaguePk,
  rounds,
}: {
  members: UserType[];
  captain: UserType | undefined;
  organizationId?: number;
  leaguePk: number | null;
  rounds?: DraftRoundType[];
}) {
  // Sort by MMR (highest first)
  const sortedMembers = useMemo(() => {
    return [...members].sort((a, b) => (b.mmr || 0) - (a.mmr || 0));
  }, [members]);

  return (
    <div className="space-y-1">
      {sortedMembers.map((member) => {
        const round = rounds?.find((r) => r.choice?.pk === member.pk);
        const isCaptain = captain?.pk === member.pk;
        const hasDuration = typeof round?.pick_duration_ms === 'number';
        const hasSkips = (round?.skip_count ?? 0) > 0;
        return (
          <UserStrip
            key={member.pk}
            user={member}
            compact
            showBorder={false}
            organizationId={organizationId}
            statsLeagueId={leaguePk}
            className="bg-base-700/30 hover:bg-base-700/50"
            contextSlot={
              isCaptain || hasDuration || hasSkips ? (
                <div className="flex items-center gap-1">
                  {isCaptain && (
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0 text-primary border-primary">
                      Captain
                    </Badge>
                  )}
                  {hasDuration && (
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0" data-testid={`pick-duration-${member.pk}`}>
                      {formatDuration((round!.pick_duration_ms as number) / 1000)}
                    </Badge>
                  )}
                  {hasSkips && (
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0 text-amber-400 border-amber-400" data-testid={`pick-skips-${member.pk}`}>
                      skipped ×{round!.skip_count}
                    </Badge>
                  )}
                </div>
              ) : undefined
            }
          />
        );
      })}
    </div>
  );
}

function TeamCard({ team, rank, organizationId, leaguePk, rounds }: TeamCardProps) {
  const { openTeamModal } = useSharedPopoverActions();
  const captain = team.captain;
  const displayName = captain ? DisplayName(captain) : team.name;

  // Calculate average MMR
  const averageMMR = useMemo(() => {
    if (!team.members || team.members.length === 0) return 0;
    const totalMMR = team.members.reduce((acc: number, member: UserType) => acc + (member.mmr || 0), 0);
    return Math.round(totalMMR / team.members.length);
  }, [team.members]);

  // Determine rank badge color
  const rankColors = [
    'bg-yellow-500 text-yellow-900', // 1st - Gold
    'bg-gray-400 text-gray-900',     // 2nd - Silver
    'bg-amber-700 text-amber-100',   // 3rd - Bronze
  ];
  const rankColor = rankColors[rank - 1] || 'bg-slate-600 text-slate-200';

  const handleClick = useCallback(() => {
    openTeamModal(team);
  }, [team, openTeamModal]);

  return (
    <Card
      className={cn(
        'w-full cursor-pointer transition-all duration-200 flex flex-col',
        'hover:ring-2 hover:ring-primary/50 hover:shadow-lg',
        'bg-slate-800/80 border-slate-700'
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
            className="ring-2 ring-slate-600"
          />

          {/* Team Name & Captain */}
          <div className="flex-1 min-w-0">
            <CardTitle className="text-lg text-white truncate" data-testid="team-card-name">
              {team.name}
            </CardTitle>
            <p className="text-sm text-slate-400 truncate">
              Captain: {displayName}
            </p>
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-0 flex-1 flex flex-col min-h-0">
        {/* Stats Row */}
        <div className="flex items-center gap-4 mb-3 shrink-0">
          <div className="flex items-center gap-1.5">
            <Trophy className="h-4 w-4 text-yellow-500" />
            <span className="text-sm font-medium text-slate-200" data-testid="team-avg-mmr-label">
              {averageMMR.toLocaleString()} avg MMR
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <Users className="h-4 w-4 text-blue-400" />
            <span className="text-sm text-slate-300">
              {team.members?.length || 0} players
            </span>
          </div>
        </div>

        {/* Tabs for Members and Position Coverage - always visible */}
        {/* Stop propagation to prevent opening team modal when clicking tabs */}
        <div onClick={(e) => e.stopPropagation()} className="flex-1 flex flex-col min-h-0">
          {/* Position coverage requires 2+ members to be meaningful */}
          {(team.members?.length || 0) >= 2 ? (
            <Tabs defaultValue="members" className="w-full flex-1 flex flex-col min-h-0">
              <TabsList className="w-full grid grid-cols-2 h-8 mb-2 shrink-0">
                <TabsTrigger value="members" className="text-xs">Members</TabsTrigger>
                <TabsTrigger value="positions" className="text-xs">Guessed Positions</TabsTrigger>
              </TabsList>
              <TabsContent value="positions" className="mt-0 flex-1 overflow-y-auto">
                <TeamPositionCoverageRow team={team} teamName={team.name || displayName} showFullTable />
              </TabsContent>
              <TabsContent value="members" className="mt-0 flex-1 overflow-y-auto">
                <TeamMembersList members={team.members || []} captain={captain} organizationId={organizationId} leaguePk={leaguePk} rounds={rounds} />
              </TabsContent>
            </Tabs>
          ) : (
            <TeamMembersList members={team.members || []} captain={captain} organizationId={organizationId} leaguePk={leaguePk} rounds={rounds} />
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// Export TeamCard and TeamMembersList for reuse in TeamsTab
export { TeamCard, TeamMembersList };

export function CompletedTeamDraftView({ teams, organizationId, leaguePk, rounds }: CompletedTeamDraftViewProps) {
  // Sort teams by average MMR (highest first)
  const sortedTeams = useMemo(() => {
    return [...teams].sort((a, b) => {
      const aMMR = a.members?.reduce((acc: number, m: UserType) => acc + (m.mmr || 0), 0) || 0;
      const bMMR = b.members?.reduce((acc: number, m: UserType) => acc + (m.mmr || 0), 0) || 0;
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
          <TeamCard key={team.pk} team={team} rank={index + 1} organizationId={organizationId} leaguePk={leaguePk} rounds={rounds} />
        ))}
      </div>
    </div>
  );
}
