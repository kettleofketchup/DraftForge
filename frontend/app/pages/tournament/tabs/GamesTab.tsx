import { memo, useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { BracketView } from '~/components/bracket';
import { GameCreateModal } from '~/components/game/create/createGameModal';
import { GameCard } from '~/components/game/gameCard/gameCard';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';

const log = getLogger('GamesTab');

export const GamesTab: React.FC = memo(() => {
  const tournament = useUserStore((state) => state.tournament);
  const isStaff = useUserStore((state) => state.isStaff());
  const [viewMode, setViewMode] = useState<'bracket' | 'list'>('bracket');

  const renderNoGames = () => {
    return (
      <div className="flex justify-center items-center h-40">
        <div className="alert alert-info">
          <span>No games available for this tournament.</span>
        </div>
      </div>
    );
  };

  const renderGamesList = () => {
    if (!tournament || !tournament.games) {
      log.error('No Tournament games');
      return renderNoGames();
    }
    log.debug('rendering games');
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {tournament.games?.map((game) => (
          <GameCard key={game.pk} game={game} />
        ))}
      </div>
    );
  };

  return (
    <div className="py-5 px-3 mx-auto container bg-base-300 rounded-lg shadow-lg" data-testid="gamesTab">
      {/* View mode tabs */}
      <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as 'bracket' | 'list')}>
        <div className="flex items-center justify-between mb-4">
          <TabsList>
            <TabsTrigger value="bracket">Bracket View</TabsTrigger>
            <TabsTrigger value="list">List View</TabsTrigger>
          </TabsList>

          {isStaff && viewMode === 'list' && (
            <GameCreateModal data-testid="gameCreateModalBtn" />
          )}
        </div>

        <TabsContent value="bracket">
          {tournament?.pk ? (
            <BracketView tournamentId={tournament.pk} />
          ) : (
            <div className="text-center text-muted-foreground py-8">
              No tournament selected
            </div>
          )}
        </TabsContent>

        <TabsContent value="list">
          {!tournament || !tournament.games || tournament.games.length === 0
            ? renderNoGames()
            : renderGamesList()}
        </TabsContent>
      </Tabs>
    </div>
  );
});

GamesTab.displayName = 'GamesTab';
