import { memo, useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { Button } from '~/components/ui/button';
import { Wand2 } from 'lucide-react';
import { BracketView } from '~/components/bracket';
import { AutoAssignModal } from '~/components/bracket/modals';
import { GameCreateModal } from '~/components/game/create/createGameModal';
import { GameCard } from '~/components/game/gameCard/gameCard';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { useBracketStore } from '~/store/bracketStore';

const log = getLogger('GamesTab');

export const GamesTab: React.FC = memo(() => {
  const tournament = useUserStore((state) => state.tournament);
  const isStaff = useUserStore((state) => state.isStaff());
  const { loadBracket } = useBracketStore();
  const [viewMode, setViewMode] = useState<'bracket' | 'list'>('bracket');
  const [showAutoAssign, setShowAutoAssign] = useState(false);

  const handleAutoAssignComplete = () => {
    if (tournament?.pk) {
      loadBracket(tournament.pk);
    }
  };

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
    <div className="py-5 px-3 mx-auto container" data-testid="gamesTab">
      {/* View mode tabs */}
      <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as 'bracket' | 'list')}>
        <div className="flex items-center justify-between mb-4">
          <TabsList>
            <TabsTrigger value="bracket">Bracket View</TabsTrigger>
            <TabsTrigger value="list">List View</TabsTrigger>
          </TabsList>

          <div className="flex items-center gap-2">
            {isStaff && viewMode === 'bracket' && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowAutoAssign(true)}
                data-testid="auto-assign-btn"
              >
                <Wand2 className="h-4 w-4 mr-1" />
                Auto-Assign Matches
              </Button>
            )}
            {isStaff && viewMode === 'list' && (
              <GameCreateModal data-testid="gameCreateModalBtn" />
            )}
          </div>
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

      {/* Auto-Assign Modal */}
      {tournament?.pk && (
        <AutoAssignModal
          isOpen={showAutoAssign}
          onClose={() => setShowAutoAssign(false)}
          tournamentId={tournament.pk}
          onAssignComplete={handleAutoAssignComplete}
        />
      )}
    </div>
  );
});

GamesTab.displayName = 'GamesTab';
