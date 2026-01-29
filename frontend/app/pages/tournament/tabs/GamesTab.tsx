import { memo, useState, useCallback } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { SecondaryButton } from '~/components/ui/buttons';
import { Wand2 } from 'lucide-react';
import { BracketView } from '~/components/bracket';
import { AutoAssignModal } from '~/components/bracket/modals';
import { GameCreateModal } from '~/components/game/create/createGameModal';
import { GameCard } from '~/components/game/gameCard/gameCard';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { useBracketStore } from '~/store/bracketStore';
import { useTournamentDataStore } from '~/store/tournamentDataStore';

const log = getLogger('GamesTab');

export const GamesTab: React.FC = memo(() => {
  // User state (keep in useUserStore)
  const isStaff = useUserStore((state) => state.isStaff());

  // Tournament data from new store (initialized by parent TournamentDetailPage)
  const tournamentId = useTournamentDataStore((state) => state.tournamentId);
  const tournamentGames = useTournamentDataStore((state) => state.games);

  // Use getState() for actions to avoid subscribing to entire store
  const [viewMode, setViewMode] = useState<'bracket' | 'list'>('bracket');
  const [showAutoAssign, setShowAutoAssign] = useState(false);

  const handleAutoAssignComplete = useCallback(() => {
    if (tournamentId) {
      // Access loadBracket via getState to avoid subscription
      useBracketStore.getState().loadBracket(tournamentId);
    }
  }, [tournamentId]);

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
    if (tournamentGames.length === 0) {
      log.error('No Tournament games');
      return renderNoGames();
    }
    log.debug('rendering games');
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {tournamentGames.map((game) => (
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
              <SecondaryButton
                color="purple"
                size="sm"
                onClick={() => setShowAutoAssign(true)}
                data-testid="auto-assign-btn"
              >
                <Wand2 className="h-4 w-4 mr-1" />
                Auto-Assign Matches
              </SecondaryButton>
            )}
            {isStaff && viewMode === 'list' && (
              <GameCreateModal data-testid="gameCreateModalBtn" />
            )}
          </div>
        </div>

        <TabsContent value="bracket">
          {tournamentId ? (
            <BracketView tournamentId={tournamentId} />
          ) : (
            <div className="text-center text-muted-foreground py-8">
              No tournament selected
            </div>
          )}
        </TabsContent>

        <TabsContent value="list">
          {tournamentGames.length === 0
            ? renderNoGames()
            : renderGamesList()}
        </TabsContent>
      </Tabs>

      {/* Auto-Assign Modal */}
      {tournamentId && (
        <AutoAssignModal
          isOpen={showAutoAssign}
          onClose={() => setShowAutoAssign(false)}
          tournamentId={tournamentId}
          onAssignComplete={handleAutoAssignComplete}
        />
      )}
    </div>
  );
});

GamesTab.displayName = 'GamesTab';
