import { memo } from 'react';
import { BracketView } from '~/components/bracket';
import { useUserStore } from '~/store/userStore';

export const GamesTab: React.FC = memo(() => {
  const tournament = useUserStore((state) => state.tournament);

  return (
    <div className="py-3 px-1 sm:py-5 sm:px-3" data-testid="gamesTab">
      {tournament?.pk ? (
        <BracketView tournamentId={tournament.pk} />
      ) : (
        <div className="text-center text-muted-foreground py-8">
          No tournament selected
        </div>
      )}
    </div>
  );
});

GamesTab.displayName = 'GamesTab';
