import { Trophy } from 'lucide-react';
import { Link } from 'react-router';
import { Badge } from '~/components/ui/badge';
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from '~/components/ui/card';
import type { LeagueListItem } from './schemas';

interface LeagueCardProps {
  league: LeagueListItem;
}

export function LeagueCard({ league }: LeagueCardProps) {
  return (
    <Link to={`/leagues/${league.pk}`}>
      <Card className="hover:bg-accent transition-colors cursor-pointer">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg flex items-center gap-2">
              <Trophy className="w-5 h-5" />
              {league.name}
            </CardTitle>
            {league.steam_league_id != null && (
              <Badge variant="secondary">#{league.steam_league_id}</Badge>
            )}
          </div>
          <CardDescription>
            {league.tournament_count} tournament
            {league.tournament_count !== 1 ? 's' : ''}
          </CardDescription>
        </CardHeader>
      </Card>
    </Link>
  );
}
