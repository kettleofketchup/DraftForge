import { memo } from 'react';
import { GameCreateModal } from '~/components/game/create/createGameModal';
import { GameCard } from '~/components/game/gameCard/gameCard';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
const log = getLogger('GamesTab');

export const GamesTab: React.FC = memo(() => {
  const tournament = useUserStore((state) => state.tournament);
  const renderNoGames = () => {
    return (
      <div className="flex justify-center items-center h-screen">
        <div className="alert alert-info">
          <span>No games available for this tournament.</span>
        </div>
      </div>
    );
  };
  const renderGames = () => {
    if (!tournament || !tournament.games) {
      log.error('No Tournament games');
      return;
    }
    log.debug('rendering games');
    return (
      <>
        {tournament.games?.map((game) => (
          <GameCard game={game} />
        ))}
      </>
    );
  };
  return (
    <div className="py-5 px-3 mx-auto container bg-base-300 rounded-lg shadow-lg hover:bg-base-400 transition-shadow duration-300 ease-in-out">
      <div className="grid grid-cols-2 gap-5 items-start pt-5  ">
        <div className="flex px-5 place-self-end">
          <GameCreateModal data-testid="gameCreateModalBtn" />
        </div>
      </div>

      {!tournament || !tournament.games || tournament.games.length === 0
        ? renderNoGames()
        : renderGames()}
    </div>
  );
});
