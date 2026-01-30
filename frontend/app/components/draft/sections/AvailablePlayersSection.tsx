import { memo, useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { Button } from '~/components/ui/button';
import { Card } from '~/components/ui/card';
import { Input } from '~/components/ui/input';
import { ScrollArea } from '~/components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';
import { DisplayName } from '~/components/user/avatar';
import { UserStrip } from '~/components/user/UserStrip';
import { ChoosePlayerButton } from '../buttons/choosePlayerButtons';
import type { TeamType } from '~/components/tournament/types';
import type { UserType } from '~/index';

const MAX_TEAM_SIZE = 5;

// Filter types
type PositionFilter = 'all' | 'carry' | 'mid' | 'offlane' | 'soft_support' | 'hard_support';
type PickOrderFilter = 'all' | 'double_pick' | 'maintains_first';
type LeagueStatsFilter = 'all' | 'high_winrate' | 'experienced' | 'new_players';

const POSITION_LABELS: Record<PositionFilter, string> = {
  all: 'All',
  carry: 'Pos 1',
  mid: 'Pos 2',
  offlane: 'Pos 3',
  soft_support: 'Pos 4',
  hard_support: 'Pos 5',
};

const PICK_ORDER_LABELS: Record<PickOrderFilter, string> = {
  all: 'All',
  double_pick: 'Double Pick',
  maintains_first: 'Stay 1st',
};

const LEAGUE_STATS_LABELS: Record<LeagueStatsFilter, string> = {
  all: 'All',
  high_winrate: 'High WR',
  experienced: '10+ Games',
  new_players: 'New',
};

// Granular selectors
const selectUsersRemaining = (state: ReturnType<typeof useUserStore.getState>) => state.draft?.users_remaining;
const selectDraftStyle = (state: ReturnType<typeof useUserStore.getState>) => state.draft?.draft_style;
const selectTeams = (state: ReturnType<typeof useUserStore.getState>) => state.tournament?.teams;
const selectCurDraftRoundCaptainPk = (state: ReturnType<typeof useUserStore.getState>) => state.curDraftRound?.captain?.pk;
const selectCurDraftRoundChoice = (state: ReturnType<typeof useUserStore.getState>) => state.curDraftRound?.choice;

// Helper to get ordinal suffix
const getOrdinal = (n: number): string => {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};

// Calculate team MMR
const getTeamMmr = (team: TeamType): number => {
  let total = team.captain?.mmr || 0;
  team.members?.forEach((member: UserType) => {
    if (member.pk !== team.captain?.pk) {
      total += member.mmr || 0;
    }
  });
  return total;
};

const isTeamMaxed = (team: TeamType): boolean => {
  return (team.members?.length || 0) >= MAX_TEAM_SIZE;
};

// Context slot for shuffle draft projections
const ShuffleProjectionSlot: React.FC<{
  projected: { newTeamMmr: number; newPickOrder: number; isDoublePick: boolean };
}> = ({ projected }) => (
  <div className="hidden sm:block">
    <div className="text-muted-foreground">
      → {projected.newTeamMmr.toLocaleString()}
    </div>
    <div
      className={cn(
        projected.isDoublePick
          ? 'text-green-400 font-medium'
          : 'text-muted-foreground'
      )}
    >
      {getOrdinal(projected.newPickOrder)}
      {projected.isDoublePick && ' 🔥'}
    </div>
  </div>
);

// Memoized player strip for the available players list
const AvailablePlayerStrip = memo(({
  user,
  isShuffle,
  projected,
}: {
  user: UserType;
  isShuffle: boolean;
  projected: { newTeamMmr: number; newPickOrder: number; isDoublePick: boolean } | null;
}) => (
  <UserStrip
    user={user}
    className={projected?.isDoublePick ? 'bg-green-950/30 border-green-500/50' : undefined}
    contextSlot={isShuffle && projected ? <ShuffleProjectionSlot projected={projected} /> : undefined}
    actionSlot={<ChoosePlayerButton user={user} />}
    data-testid="available-player"
  />
));
AvailablePlayerStrip.displayName = 'AvailablePlayerStrip';

export const AvailablePlayersSection = memo(() => {
  const usersRemaining = useUserStore(selectUsersRemaining);
  const draftStyle = useUserStore(selectDraftStyle);
  const teams = useUserStore(selectTeams);
  const curDraftRoundCaptainPk = useUserStore(selectCurDraftRoundCaptainPk);
  const curDraftRoundChoice = useUserStore(selectCurDraftRoundChoice);

  // Filter states
  const [searchQuery, setSearchQuery] = useState('');
  const [positionFilter, setPositionFilter] = useState<PositionFilter>('all');
  const [pickOrderFilter, setPickOrderFilter] = useState<PickOrderFilter>('all');
  const [leagueStatsFilter, setLeagueStatsFilter] = useState<LeagueStatsFilter>('all');

  const isShuffle = draftStyle === 'shuffle';

  // Get current team
  const currentTeam = useMemo(() => {
    return teams?.find((t) => t.captain?.pk === curDraftRoundCaptainPk);
  }, [teams, curDraftRoundCaptainPk]);

  // Get available players sorted by MMR
  const availablePlayers = useMemo(() => {
    return (
      usersRemaining?.slice().sort((a: UserType, b: UserType): number => {
        if (!a.mmr && !b.mmr) return 0;
        if (!a.mmr) return 1;
        if (!b.mmr) return -1;
        if (a.mmr === b.mmr) {
          return (a.username || '').localeCompare(b.username || '');
        }
        return b.mmr - a.mmr;
      }) || []
    );
  }, [usersRemaining]);

  // Helper to check if a player would result in double pick
  const wouldDoublePick = (userMmr: number): boolean => {
    if (!currentTeam) return false;
    const currentTeamMmr = getTeamMmr(currentTeam);
    const newTeamMmr = currentTeamMmr + userMmr;
    const otherActiveTeams = (teams || [])
      .filter((t) => t.pk !== currentTeam.pk && !isTeamMaxed(t));
    if (otherActiveTeams.length === 0) return true;
    const lowestOtherMmr = Math.min(...otherActiveTeams.map((t) => getTeamMmr(t)));
    const wouldBeMaxed = (currentTeam.members?.length || 0) + 1 >= MAX_TEAM_SIZE;
    return !wouldBeMaxed && newTeamMmr < lowestOtherMmr;
  };

  // Helper to check if picking would maintain first pick
  const wouldMaintainFirst = (userMmr: number): boolean => {
    if (!currentTeam) return false;
    const currentTeamMmr = getTeamMmr(currentTeam);
    const newTeamMmr = currentTeamMmr + userMmr;
    const otherActiveTeams = (teams || [])
      .filter((t) => t.pk !== currentTeam.pk && !isTeamMaxed(t));
    if (otherActiveTeams.length === 0) return true;
    const lowestOtherMmr = Math.min(...otherActiveTeams.map((t) => getTeamMmr(t)));
    return newTeamMmr <= lowestOtherMmr;
  };

  // Filter players by all criteria
  const filteredPlayers = useMemo(() => {
    let players = availablePlayers;

    // Search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      players = players.filter((user) =>
        (user.username || '').toLowerCase().includes(query) ||
        (user.nickname || '').toLowerCase().includes(query)
      );
    }

    // Position filter
    if (positionFilter !== 'all') {
      players = players.filter((user) => {
        const positions = user.positions;
        if (!positions) return false;
        return (positions[positionFilter] || 0) > 0;
      });
    }

    // Pick order filter (shuffle only)
    if (isShuffle && pickOrderFilter !== 'all') {
      players = players.filter((user) => {
        const mmr = user.mmr || 0;
        if (pickOrderFilter === 'double_pick') return wouldDoublePick(mmr);
        if (pickOrderFilter === 'maintains_first') return wouldMaintainFirst(mmr);
        return true;
      });
    }

    // League stats filter
    if (leagueStatsFilter !== 'all') {
      players = players.filter((user) => {
        const extended = user as UserType & { games_played?: number; win_rate?: number };
        if (leagueStatsFilter === 'high_winrate') return (extended.win_rate || 0) >= 55;
        if (leagueStatsFilter === 'experienced') return (extended.games_played || 0) >= 10;
        if (leagueStatsFilter === 'new_players') return (extended.games_played || 0) < 5;
        return true;
      });
    }

    return players;
  }, [availablePlayers, searchQuery, positionFilter, pickOrderFilter, leagueStatsFilter, isShuffle, currentTeam, teams]);

  // Split players into columns (newspaper style)
  const { col1, col2, col3, leftCol, rightCol } = useMemo(() => {
    const threeCol: [UserType[], UserType[], UserType[]] = [[], [], []];
    filteredPlayers.forEach((player, idx) => {
      threeCol[idx % 3].push(player);
    });
    const twoCol: [UserType[], UserType[]] = [[], []];
    filteredPlayers.forEach((player, idx) => {
      twoCol[idx % 2].push(player);
    });
    return {
      col1: threeCol[0],
      col2: threeCol[1],
      col3: threeCol[2],
      leftCol: twoCol[0],
      rightCol: twoCol[1],
    };
  }, [filteredPlayers]);

  // Projected data for shuffle mode
  const getProjectedData = (userMmr: number) => {
    if (!isShuffle || !currentTeam) return null;

    const currentTeamMmr = getTeamMmr(currentTeam);
    const newTeamMmr = currentTeamMmr + userMmr;

    const otherActiveTeams = (teams || [])
      .filter((t) => t.pk !== currentTeam.pk && !isTeamMaxed(t));

    if (otherActiveTeams.length === 0) {
      return { newTeamMmr, newPickOrder: 1, isDoublePick: true };
    }

    const otherMmrs = otherActiveTeams.map((t) => getTeamMmr(t));
    const allMmrs = [...otherMmrs, newTeamMmr].sort((a, b) => a - b);
    const newPickOrder = allMmrs.indexOf(newTeamMmr) + 1;

    const wouldBeMaxedAfterPick = (currentTeam.members?.length || 0) + 1 >= MAX_TEAM_SIZE;
    const lowestOtherMmr = Math.min(...otherMmrs);
    const isDoublePick = !wouldBeMaxedAfterPick && newTeamMmr < lowestOtherMmr;

    return { newTeamMmr, newPickOrder, isDoublePick };
  };

  // If already picked, show the result
  if (curDraftRoundChoice) {
    return (
      <div className="flex-1 min-h-[180px] md:min-h-[250px] flex flex-col">
        <Card className="h-full flex items-center justify-center">
          <p className="text-lg font-semibold text-green-400">
            Picked: {DisplayName(curDraftRoundChoice)}
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex-1 min-h-[180px] md:min-h-[250px] flex flex-col">
      {/* Search + Filter Tabs */}
      <div className="shrink-0 space-y-2 mb-3">
        {/* Search Bar */}
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search players..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8 h-8 text-sm"
          />
        </div>

        {/* Filter Tabs */}
        <Tabs defaultValue="positions" className="w-full">
          <TabsList className="grid w-full grid-cols-3 h-8">
            <TabsTrigger value="positions" className="text-xs">Positions</TabsTrigger>
            {isShuffle && <TabsTrigger value="pickorder" className="text-xs">Pick Order</TabsTrigger>}
            {!isShuffle && <TabsTrigger value="pickorder" disabled className="text-xs opacity-50">Pick Order</TabsTrigger>}
            <TabsTrigger value="league" className="text-xs">League</TabsTrigger>
          </TabsList>

          <TabsContent value="positions" className="mt-2">
            <div className="flex flex-wrap gap-1">
              {(Object.keys(POSITION_LABELS) as PositionFilter[]).map((pos) => (
                <Button
                  key={pos}
                  size="sm"
                  variant={positionFilter === pos ? 'default' : 'outline'}
                  onClick={() => setPositionFilter(pos)}
                  className="text-xs px-2 py-0.5 h-6"
                >
                  {POSITION_LABELS[pos]}
                </Button>
              ))}
            </div>
          </TabsContent>

          <TabsContent value="pickorder" className="mt-2">
            <div className="flex flex-wrap gap-1">
              {(Object.keys(PICK_ORDER_LABELS) as PickOrderFilter[]).map((filter) => (
                <Button
                  key={filter}
                  size="sm"
                  variant={pickOrderFilter === filter ? 'default' : 'outline'}
                  onClick={() => setPickOrderFilter(filter)}
                  className="text-xs px-2 py-0.5 h-6"
                  disabled
                >
                  {PICK_ORDER_LABELS[filter]}
                </Button>
              ))}
            </div>
          </TabsContent>

          <TabsContent value="league" className="mt-2">
            <div className="flex flex-wrap gap-1">
              {(Object.keys(LEAGUE_STATS_LABELS) as LeagueStatsFilter[]).map((filter) => (
                <Button
                  key={filter}
                  size="sm"
                  variant={leagueStatsFilter === filter ? 'default' : 'outline'}
                  onClick={() => setLeagueStatsFilter(filter)}
                  className="text-xs px-2 py-0.5 h-6"
                  disabled
                >
                  {LEAGUE_STATS_LABELS[filter]}
                </Button>
              ))}
            </div>
          </TabsContent>
        </Tabs>

        <div className="text-[13px] text-muted-foreground">
          {filteredPlayers.length}/{availablePlayers.length} players
          {filteredPlayers.length < availablePlayers.length && (
            <span className="text-yellow-500/80 ml-1">
              ({availablePlayers.length - filteredPlayers.length} hidden)
            </span>
          )}
        </div>
      </div>

      {/* XL screens: Three columns */}
      <div className="hidden xl:grid xl:grid-cols-3 gap-2 flex-1 min-h-0">
        <ScrollArea className="h-full">
          <div className="space-y-1.5 pr-2">
            {col1.map((user) => (
              <AvailablePlayerStrip
                key={user.pk}
                user={user}
                isShuffle={isShuffle}
                projected={getProjectedData(user.mmr || 0)}
              />
            ))}
          </div>
        </ScrollArea>
        <ScrollArea className="h-full">
          <div className="space-y-1.5 pr-2">
            {col2.map((user) => (
              <AvailablePlayerStrip
                key={user.pk}
                user={user}
                isShuffle={isShuffle}
                projected={getProjectedData(user.mmr || 0)}
              />
            ))}
          </div>
        </ScrollArea>
        <ScrollArea className="h-full">
          <div className="space-y-1.5 pr-2">
            {col3.map((user) => (
              <AvailablePlayerStrip
                key={user.pk}
                user={user}
                isShuffle={isShuffle}
                projected={getProjectedData(user.mmr || 0)}
              />
            ))}
          </div>
        </ScrollArea>
      </div>

      {/* Medium-Large screens: Two columns */}
      <div className="hidden md:grid xl:hidden md:grid-cols-2 gap-2 flex-1 min-h-0">
        <ScrollArea className="h-full">
          <div className="space-y-1.5 pr-2">
            {leftCol.map((user) => (
              <AvailablePlayerStrip
                key={user.pk}
                user={user}
                isShuffle={isShuffle}
                projected={getProjectedData(user.mmr || 0)}
              />
            ))}
          </div>
        </ScrollArea>
        <ScrollArea className="h-full">
          <div className="space-y-1.5 pr-2">
            {rightCol.map((user) => (
              <AvailablePlayerStrip
                key={user.pk}
                user={user}
                isShuffle={isShuffle}
                projected={getProjectedData(user.mmr || 0)}
              />
            ))}
          </div>
        </ScrollArea>
      </div>

      {/* Small screens: Single column */}
      <ScrollArea className="md:hidden flex-1">
        <div className="space-y-1.5 pr-2">
          {filteredPlayers.map((user) => (
            <AvailablePlayerStrip
              key={user.pk}
              user={user}
              isShuffle={isShuffle}
              projected={getProjectedData(user.mmr || 0)}
            />
          ))}
        </div>
      </ScrollArea>
    </div>
  );
});

AvailablePlayersSection.displayName = 'AvailablePlayersSection';
