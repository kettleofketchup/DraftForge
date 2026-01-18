import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { InfoTab } from './tabs/InfoTab';
import { TournamentsTab } from './tabs/TournamentsTab';
import { MatchesTab } from './tabs/MatchesTab';
import type { LeagueType } from './schemas';
import type { TournamentType } from '~/components/tournament/types';

interface Props {
  league: LeagueType;
  tournaments: TournamentType[];
  activeTab: string;
  onTabChange: (tab: string) => void;
}

export const LeagueTabs: React.FC<Props> = ({
  league,
  tournaments,
  activeTab,
  onTabChange,
}) => {
  return (
    <Tabs value={activeTab} onValueChange={onTabChange} className="w-full">
      <TabsList className="grid w-full grid-cols-3">
        <TabsTrigger value="info" data-testid="league-tab-info">
          Info
        </TabsTrigger>
        <TabsTrigger value="tournaments" data-testid="league-tab-tournaments">
          Tournaments ({tournaments.length})
        </TabsTrigger>
        <TabsTrigger value="matches" data-testid="league-tab-matches">
          Matches
        </TabsTrigger>
      </TabsList>

      <TabsContent value="info" className="mt-6">
        <InfoTab league={league} />
      </TabsContent>

      <TabsContent value="tournaments" className="mt-6">
        <TournamentsTab league={league} tournaments={tournaments} />
      </TabsContent>

      <TabsContent value="matches" className="mt-6">
        {league.pk && <MatchesTab leaguePk={league.pk} />}
      </TabsContent>
    </Tabs>
  );
};
