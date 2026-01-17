import { memo, useMemo } from 'react';
import { Construction } from 'lucide-react';
import { Button } from '~/components/ui/button';
import { Progress } from '~/components/ui/progress';
import { useTangoes } from '~/hooks/useTangoes';
import { useUserStore } from '~/store/userStore';

const GAMES_TO_THROW = 10;
const GAMES_THROWN = 2; // Always 2/10 - it's a joke
const TANGOES_REQUIRED = 46326;

interface PlayerUnderConstructionProps {
  playerName: string;
}

export const PlayerUnderConstruction: React.FC<PlayerUnderConstructionProps> = memo(({
  playerName,
}) => {
  const currentUser = useUserStore((state) => state.currentUser);
  const isLoggedIn = !!currentUser?.pk;
  const { tangoes, buyTango, isBuying, isLoading } = useTangoes(isLoggedIn);

  const gamesProgress = useMemo(
    () => (GAMES_THROWN / GAMES_TO_THROW) * 100,
    []
  );

  const tangoesProgress = useMemo(
    () => Math.min((tangoes / TANGOES_REQUIRED) * 100, 100),
    [tangoes]
  );

  return (
    <div className="border border-dashed border-yellow-500/50 rounded-lg p-4 bg-yellow-950/10">
      <div className="flex items-center justify-center gap-2 mb-4">
        <Construction className="h-5 w-5 text-yellow-500" aria-hidden="true" />
        <h3 className="text-lg font-semibold text-yellow-500">
          EXTENDED PROFILE UNDER CONSTRUCTION
        </h3>
        <Construction className="h-5 w-5 text-yellow-500" aria-hidden="true" />
      </div>

      <p className="text-center text-muted-foreground mb-4">
        To unlock {playerName}'s extended profile:
      </p>

      {/* Option A: Throw games */}
      <div className="border border-muted rounded-lg p-3 mb-3">
        <p className="font-medium mb-2">
          Option A: Throw {GAMES_TO_THROW} of {playerName}'s games
        </p>
        <div className="flex items-center gap-2">
          <Progress
            value={gamesProgress}
            className="flex-1"
            aria-label={`${GAMES_THROWN} of ${GAMES_TO_THROW} games thrown`}
          />
          <span className="text-sm text-muted-foreground whitespace-nowrap">
            {GAMES_THROWN}/{GAMES_TO_THROW} games thrown
          </span>
        </div>
      </div>

      <p className="text-center text-muted-foreground my-2">— OR —</p>

      {/* Option B: Buy tangoes */}
      <div className="border border-muted rounded-lg p-3">
        <p className="font-medium mb-2">
          Option B: Purchase {TANGOES_REQUIRED.toLocaleString()} tangoes
        </p>
        <div className="flex items-center gap-2 mb-2">
          <span className="text-lg" aria-hidden="true">🌿</span>
          <Progress
            value={tangoesProgress}
            className="flex-1"
            aria-label={`${tangoes} of ${TANGOES_REQUIRED} tangoes purchased`}
          />
          <span className="text-sm text-muted-foreground whitespace-nowrap">
            {tangoes.toLocaleString()} / {TANGOES_REQUIRED.toLocaleString()}
          </span>
        </div>
        {isLoggedIn ? (
          <Button
            variant="outline"
            size="sm"
            onClick={buyTango}
            disabled={isBuying || isLoading}
            className="w-full"
            aria-busy={isBuying}
          >
            🌿 {isBuying ? 'Buying...' : 'Buy Tango'}
          </Button>
        ) : (
          <p className="text-sm text-muted-foreground text-center">
            Log in to purchase tangoes
          </p>
        )}
      </div>
    </div>
  );
});

PlayerUnderConstruction.displayName = 'PlayerUnderConstruction';
