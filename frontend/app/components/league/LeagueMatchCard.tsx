import { format } from 'date-fns';
import { Calendar, Trophy, Link as LinkIcon } from 'lucide-react';
import { useState } from 'react';

import { Card, CardContent } from '~/components/ui/card';
import { Badge } from '~/components/ui/badge';
import { Button } from '~/components/ui/button';
import { UserAvatar } from '~/components/user/UserAvatar';
import { PlayerPopover } from '~/components/player/PlayerPopover';
import { DotaMatchStatsModal } from '~/components/bracket/modals/DotaMatchStatsModal';
import { cn } from '~/lib/utils';
import type { LeagueMatchType } from './schemas';
import type { UserType } from '~/components/user/types';

interface Props {
  match: LeagueMatchType;
}

export const LeagueMatchCard: React.FC<Props> = ({ match }) => {
  const [showStats, setShowStats] = useState(false);

  const radiantWon = match.winning_team === match.radiant_team;
  const direWon = match.winning_team === match.dire_team;
  const hasResult = match.winning_team !== null;
  const hasSteamLink = !!match.gameid;

  return (
    <>
      <Card className="hover:shadow-md transition-shadow" data-testid={`league-match-card-${match.pk}`}>
        <CardContent className="p-4">
          {/* Header: Tournament + Round */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Trophy className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">
                {match.tournament_name || 'Direct Match'}
              </span>
              {match.round && (
                <Badge variant="outline" className="text-xs">
                  Round {match.round}
                </Badge>
              )}
            </div>
            {hasSteamLink && (
              <Badge variant="secondary" className="text-xs">
                <LinkIcon className="h-3 w-3 mr-1" />
                Steam Linked
              </Badge>
            )}
          </div>

          {/* Captains Display */}
          <div className="flex items-center justify-between gap-4">
            {/* Radiant Captain */}
            <div
              className={cn(
                'flex items-center gap-3 flex-1',
                radiantWon && 'ring-2 ring-green-500 rounded-lg p-2'
              )}
            >
              {match.radiant_captain ? (
                <PlayerPopover player={match.radiant_captain}>
                  <div className="flex items-center gap-2 cursor-pointer">
                    <UserAvatar user={match.radiant_captain} size="lg" />
                    <div>
                      <p className="font-medium text-green-600">
                        {match.radiant_captain.nickname ||
                          match.radiant_captain.username}
                      </p>
                      <p className="text-xs text-muted-foreground">Radiant</p>
                    </div>
                  </div>
                </PlayerPopover>
              ) : (
                <div className="text-muted-foreground">TBD</div>
              )}
            </div>

            {/* VS / Score */}
            <div className="text-center px-4">
              {hasResult ? (
                <div className="text-lg font-bold">
                  <span
                    className={
                      radiantWon ? 'text-green-600' : 'text-muted-foreground'
                    }
                  >
                    {radiantWon ? 'W' : 'L'}
                  </span>
                  <span className="mx-2">-</span>
                  <span
                    className={
                      direWon ? 'text-red-600' : 'text-muted-foreground'
                    }
                  >
                    {direWon ? 'W' : 'L'}
                  </span>
                </div>
              ) : (
                <span className="text-muted-foreground font-medium">vs</span>
              )}
            </div>

            {/* Dire Captain */}
            <div
              className={cn(
                'flex items-center gap-3 flex-1 justify-end',
                direWon && 'ring-2 ring-red-500 rounded-lg p-2'
              )}
            >
              {match.dire_captain ? (
                <PlayerPopover player={match.dire_captain}>
                  <div className="flex items-center gap-2 cursor-pointer">
                    <div className="text-right">
                      <p className="font-medium text-red-600">
                        {match.dire_captain.nickname ||
                          match.dire_captain.username}
                      </p>
                      <p className="text-xs text-muted-foreground">Dire</p>
                    </div>
                    <UserAvatar user={match.dire_captain} size="lg" />
                  </div>
                </PlayerPopover>
              ) : (
                <div className="text-muted-foreground">TBD</div>
              )}
            </div>
          </div>

          {/* Footer: Date + Actions */}
          <div className="flex items-center justify-between mt-4 pt-3 border-t">
            <div className="flex items-center gap-4 text-sm text-muted-foreground">
              {match.date_played && (
                <div className="flex items-center gap-1">
                  <Calendar className="h-4 w-4" />
                  {format(new Date(match.date_played), 'MMM d, yyyy')}
                </div>
              )}
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowStats(true)}
              disabled={!hasSteamLink}
            >
              View Details
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Stats Modal - uses onClose and matchId props */}
      {hasSteamLink && (
        <DotaMatchStatsModal
          open={showStats}
          onClose={() => setShowStats(false)}
          matchId={match.gameid}
        />
      )}
    </>
  );
};
