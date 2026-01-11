import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '~/components/ui/dialog';
import { Button } from '~/components/ui/button';
import { Badge } from '~/components/ui/badge';
import { Avatar, AvatarFallback, AvatarImage } from '~/components/ui/avatar';
import { BarChart3, Link2 } from 'lucide-react';
import { useUserStore } from '~/store/userStore';
import { useBracketStore } from '~/store/bracketStore';
import { DotaMatchStatsModal } from './DotaMatchStatsModal';
import { LinkSteamMatchModal } from './LinkSteamMatchModal';
import type { BracketMatch } from '../types';
import { cn } from '~/lib/utils';

interface MatchStatsModalProps {
  match: BracketMatch | null;
  isOpen: boolean;
  onClose: () => void;
}

export function MatchStatsModal({ match, isOpen, onClose }: MatchStatsModalProps) {
  const isStaff = useUserStore((state) => state.isStaff());
  const tournament = useUserStore((state) => state.tournament);
  const { setMatchWinner, advanceWinner, loadBracket } = useBracketStore();
  const [showStatsModal, setShowStatsModal] = useState(false);
  const [showLinkModal, setShowLinkModal] = useState(false);

  if (!match) return null;

  const isGameComplete = match.status === 'completed';
  const hasMatchId = !!match.steamMatchId;

  const handleSetWinner = (winner: 'radiant' | 'dire') => {
    setMatchWinner(match.id, winner);
    advanceWinner(match.id);
  };

  const handleLinkUpdated = () => {
    if (tournament?.pk) {
      loadBracket(tournament.pk);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Match Details</DialogTitle>
          <DialogDescription>
            {match.bracketType === 'grand_finals'
              ? 'Grand Finals'
              : `${match.bracketType === 'winners' ? 'Winners' : 'Losers'} Round ${match.round}`}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Teams display */}
          <div className="grid grid-cols-3 gap-4 items-center py-4">
            {/* Radiant team */}
            <TeamCard
              team={match.radiantTeam}
              score={match.radiantScore}
              isWinner={match.winner === 'radiant'}
              label="Radiant"
            />

            {/* VS divider */}
            <div className="text-center">
              <span className="text-2xl font-bold text-muted-foreground">VS</span>
              {match.status === 'completed' && (
                <Badge className="block mt-2" variant="outline">
                  Final
                </Badge>
              )}
              {match.status === 'live' && (
                <Badge className="block mt-2 bg-red-500">LIVE</Badge>
              )}
            </div>

            {/* Dire team */}
            <TeamCard
              team={match.direTeam}
              score={match.direScore}
              isWinner={match.winner === 'dire'}
              label="Dire"
            />
          </div>

          {/* Staff controls */}
          {isStaff && match.status !== 'completed' && match.radiantTeam && match.direTeam && (
            <div className="border-t pt-4">
              <p className="text-sm text-muted-foreground mb-2">Set Winner:</p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => handleSetWinner('radiant')}
                >
                  {match.radiantTeam.name} Wins
                </Button>
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => handleSetWinner('dire')}
                >
                  {match.direTeam.name} Wins
                </Button>
              </div>
            </div>
          )}

          {/* Steam match info and Stats button */}
          {hasMatchId && (
            <div className="border-t pt-4">
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  Steam Match ID: {match.steamMatchId}
                </p>
                {isGameComplete && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setShowStatsModal(true)}
                  >
                    <BarChart3 className="w-4 h-4 mr-1" />
                    View Stats
                  </Button>
                )}
              </div>
            </div>
          )}

          {/* Staff: Link Steam Match button */}
          {isStaff && (
            <div className="border-t pt-4">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowLinkModal(true)}
                data-testid="link-steam-match-btn"
              >
                <Link2 className="w-4 h-4 mr-1" />
                {match.steamMatchId
                  ? `Linked: Match #${match.steamMatchId}`
                  : 'Link Steam Match'}
              </Button>
            </div>
          )}
        </div>

        {/* Detailed Match Stats Modal */}
        <DotaMatchStatsModal
          open={showStatsModal}
          onClose={() => setShowStatsModal(false)}
          matchId={match.steamMatchId ?? null}
        />

        {/* Link Steam Match Modal */}
        <LinkSteamMatchModal
          isOpen={showLinkModal}
          onClose={() => setShowLinkModal(false)}
          game={match}
          onLinkUpdated={handleLinkUpdated}
        />
      </DialogContent>
    </Dialog>
  );
}

interface TeamCardProps {
  team?: { name: string; captain?: { avatarUrl?: string; username?: string } };
  score?: number;
  isWinner: boolean;
  label: string;
}

function TeamCard({ team, score, isWinner, label }: TeamCardProps) {
  if (!team) {
    return (
      <div className="text-center p-4 rounded-lg bg-muted/50">
        <div className="h-12 w-12 rounded-full bg-muted mx-auto mb-2" />
        <p className="text-sm text-muted-foreground">TBD</p>
      </div>
    );
  }

  const displayName = team.captain?.username ?? team.name;
  const initials = displayName.substring(0, 2).toUpperCase();

  return (
    <div
      className={cn(
        'text-center p-4 rounded-lg',
        isWinner ? 'bg-green-500/10 ring-2 ring-green-500' : 'bg-muted/50'
      )}
    >
      <Avatar className="h-12 w-12 mx-auto mb-2">
        <AvatarImage src={team.captain?.avatarUrl} />
        <AvatarFallback>{initials}</AvatarFallback>
      </Avatar>
      <p className={cn('font-medium', isWinner && 'text-green-500')}>{displayName}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
      {score !== undefined && (
        <p className={cn('text-2xl font-bold mt-1', isWinner && 'text-green-500')}>
          {score}
        </p>
      )}
      {isWinner && <span className="text-green-500">Winner</span>}
    </div>
  );
}
