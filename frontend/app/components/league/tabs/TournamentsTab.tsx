import { Trophy } from 'lucide-react';
import { useState } from 'react';

import { TournamentCard } from '~/components/tournament/card/TournamentCard';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import type { LeagueType } from '../schemas';
import type { TournamentType } from '~/components/tournament/types';

interface Props {
  league: LeagueType;
  tournaments: TournamentType[];
}

export const TournamentsTab: React.FC<Props> = ({ league, tournaments }) => {
  const [stateFilter, setStateFilter] = useState<string>('all');

  const filteredTournaments = tournaments.filter((t) => {
    if (stateFilter === 'all') return true;
    return t.state === stateFilter;
  });

  return (
    <div className="space-y-4">
      {/* Filter */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium flex items-center gap-2">
          <Trophy className="h-5 w-5" />
          Tournaments ({filteredTournaments.length})
        </h3>
        <Select value={stateFilter} onValueChange={setStateFilter}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Filter by state" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All States</SelectItem>
            <SelectItem value="future">Future</SelectItem>
            <SelectItem value="in_progress">In Progress</SelectItem>
            <SelectItem value="past">Past</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Tournament Grid */}
      {filteredTournaments.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredTournaments.map((tournament) => (
            <TournamentCard key={tournament.pk} tournament={tournament} />
          ))}
        </div>
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          No tournaments found for this league.
        </div>
      )}
    </div>
  );
};
