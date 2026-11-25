import { BadgeCheck, Users } from 'lucide-react';
import type { TournamentType } from '~/components/tournament/types';
import { Badge } from '~/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { MmrRequestsTab, useMmrPendingCount } from '~/features/mmr-requests';
import { memberCountDisplay } from '~/lib/memberCountDisplay';
import { useLeagueStore } from '~/store/leagueStore';
import type { LeagueType } from './schemas';
import { InfoTab } from './tabs/InfoTab';
import { LobbyBotsTab } from './tabs/LobbyBotsTab';
import { MatchesTab } from './tabs/MatchesTab';
import { TournamentsTab } from './tabs/TournamentsTab';
import { UsersTab } from './tabs/UsersTab';

interface Props {
  league: LeagueType;
  tournaments: TournamentType[];
  activeTab: string;
  onTabChange: (tab: string) => void;
  canViewMembers: boolean;
  memberAccessSettled: boolean;
  canReviewMmr?: boolean;
  canManageLobbyBots: boolean;
  lobbyBotsAccessSettled: boolean;
}

const GRID_COLS: Record<number, string> = {
  3: 'grid-cols-3',
  4: 'grid-cols-4',
  5: 'grid-cols-5',
  6: 'grid-cols-6',
};

export const LeagueTabs: React.FC<Props> = ({
  league,
  tournaments,
  activeTab,
  onTabChange,
  canViewMembers,
  memberAccessSettled,
  canReviewMmr = false,
  canManageLobbyBots,
  lobbyBotsAccessSettled,
}) => {
  const leagueUserPks = useLeagueStore((state) => state.leagueUserPks);
  const leagueUsersLoading = useLeagueStore(
    (state) => state.leagueUsersLoading,
  );
  const leagueUsersLeagueId = useLeagueStore(
    (state) => state.leagueUsersLeagueId,
  );

  const userCountDisplay = memberCountDisplay({
    entityId: league.pk,
    loadedForId: leagueUsersLeagueId,
    loading: leagueUsersLoading,
    loadedCount: leagueUserPks.length,
    fallbackCount: league.users_count,
  });
  const leaguePk = league.pk ?? 0;
  const mmrPendingCount =
    useMmrPendingCount({ league: leaguePk }, canReviewMmr && leaguePk > 0).data
      ?.count ?? 0;
  const tabCount =
    3 +
    (canViewMembers ? 1 : 0) +
    (canReviewMmr ? 1 : 0) +
    (canManageLobbyBots ? 1 : 0);

  return (
    <Tabs value={activeTab} onValueChange={onTabChange} className="w-full">
      <TabsList className={`hidden md:grid w-full ${GRID_COLS[tabCount]}`}>
        <TabsTrigger value="info" data-testid="league-tab-info">
          Info
        </TabsTrigger>
        <TabsTrigger value="tournaments" data-testid="league-tab-tournaments">
          Tournaments ({tournaments.length})
        </TabsTrigger>
        {canViewMembers && (
          <TabsTrigger value="users" data-testid="league-tab-users">
            <Users className="w-4 h-4 mr-2" />
            Users ({userCountDisplay})
          </TabsTrigger>
        )}
        <TabsTrigger value="matches" data-testid="league-tab-matches">
          Matches
        </TabsTrigger>
        {canReviewMmr && (
          <TabsTrigger
            value="mmr-requests"
            data-testid="league-tab-mmr-requests"
          >
            <BadgeCheck className="w-4 h-4 mr-2" />
            MMR requests
            {mmrPendingCount > 0 && (
              <Badge
                variant="secondary"
                className="ml-2 text-xs"
                data-testid="league-tab-mmr-requests-count"
              >
                {mmrPendingCount}
              </Badge>
            )}
          </TabsTrigger>
        )}
        {canManageLobbyBots && (
          <TabsTrigger value="lobby-bots" data-testid="league-tab-lobby-bots">
            Lobby bots
          </TabsTrigger>
        )}
      </TabsList>

      <TabsContent value="info" className="mt-6">
        <InfoTab league={league} />
      </TabsContent>

      <TabsContent value="tournaments" className="mt-6">
        <TournamentsTab league={league} tournaments={tournaments} />
      </TabsContent>

      {canViewMembers && (
        <TabsContent value="users" className="mt-6">
          {league.pk && (
            <UsersTab leaguePk={league.pk} canLoad={memberAccessSettled} />
          )}
        </TabsContent>
      )}

      <TabsContent value="matches" className="mt-6">
        {league.pk && <MatchesTab leaguePk={league.pk} />}
      </TabsContent>

      {canReviewMmr && league.pk && (
        <TabsContent value="mmr-requests" className="mt-6">
          <MmrRequestsTab scope={{ league: league.pk }} />
        </TabsContent>
      )}

      {canManageLobbyBots && (
        <TabsContent value="lobby-bots" className="mt-6">
          {league.pk && (
            <LobbyBotsTab
              leaguePk={league.pk}
              enabled={lobbyBotsAccessSettled}
            />
          )}
        </TabsContent>
      )}
    </Tabs>
  );
};
