import type { JSX } from 'react';
import { toast } from 'sonner';
import { createGame } from '~/components/api/api';
import type { GameType } from '~/index';
import { getLogger } from '~/lib/logger';
const log = getLogger('Create Game Hook');
type hookParams = {
  game: GameType;
};
const createErrorMessage = (
  val: Partial<Record<keyof GameType, string>>,
): JSX.Element => {
  const headerText = () => <h5>Error creating Game:</h5>;
  if (!val || Object.keys(val).length === 0) return headerText();

  return (
    <div className="text-error">
      {headerText()}
      <ul>
        {Object.entries(val).map(([field, message]) => (
          <li key={field}>{message}</li>
        ))}
      </ul>
    </div>
  );
};
export const createGameHook = async ({ game }: hookParams) => {
  log.debug('Creating Game', { game });

  const data: GameType = {
    radiant_team_id: game.radiant_team?.pk,
    dire_team_id: game.radiant_team?.pk,
    ...game,
  };

  data.radiant_team = undefined;
  data.dire_team = undefined;

  toast.promise(createGame(data), {
    loading: `Creating Game ...`,
    success: (data) => {
      return `Game has been created!`;
    },
    error: (err) => {
      const val = err.response.data;
      log.error('Game has has failed to be created!', err);
      return <>{createErrorMessage(val)}</>;
    },
  });
};
