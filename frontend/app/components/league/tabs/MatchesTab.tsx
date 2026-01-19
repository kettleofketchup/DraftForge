import { Gamepad2, Loader2, Check } from 'lucide-react';
import { useState } from 'react';

import { LeagueMatchCard } from '../LeagueMatchCard';
import { useLeagueMatches } from '../hooks/useLeagueMatches';
import { Button } from '~/components/ui/button';

interface Props {
  leaguePk: number;
}

export const MatchesTab: React.FC<Props> = ({ leaguePk }) => {
  const [linkedOnly, setLinkedOnly] = useState(false);
  const { matches, isLoading, error } = useLeagueMatches(leaguePk, { linkedOnly });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12 text-destructive">
        Failed to load matches: {error.message}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium flex items-center gap-2">
          <Gamepad2 className="h-5 w-5" />
          Matches ({matches.length})
        </h3>
        <Button
          variant={linkedOnly ? 'default' : 'outline'}
          size="sm"
          onClick={() => setLinkedOnly(!linkedOnly)}
        >
          {linkedOnly && <Check className="h-4 w-4 mr-1" />}
          Steam linked only
        </Button>
      </div>

      {/* Match List */}
      {matches.length > 0 ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {matches.map((match) => (
            <LeagueMatchCard key={match.pk} match={match} />
          ))}
        </div>
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          No matches found for this league.
        </div>
      )}
    </div>
  );
};
