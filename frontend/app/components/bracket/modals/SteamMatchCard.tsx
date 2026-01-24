import { Avatar, AvatarFallback, AvatarImage } from '~/components/ui/avatar';
import { Button } from '~/components/ui/button';
import { User } from 'lucide-react';
import { cn } from '~/lib/utils';
import { UserPopover } from '~/components/user/UserPopover';

export interface CaptainInfo {
  steam_id: number;
  username: string | null;
  avatar: string | null;
  hero_id: number;
}

export interface MatchedPlayer {
  steam_id: number;
  user_id: number | null;
  username: string | null;
  avatar: string | null;
  hero_id: number;
  player_slot: number;
  is_radiant: boolean;
  is_captain: boolean;
}

export interface MatchSuggestion {
  match_id: number;
  start_time: number;
  duration: number;
  radiant_win: boolean;
  tier: string;
  tier_display: string;
  player_overlap: number;
  radiant_captain: CaptainInfo | null;
  dire_captain: CaptainInfo | null;
  matched_players: MatchedPlayer[];
}

interface SteamMatchCardProps {
  match: MatchSuggestion;
  onLink: (matchId: number) => void;
  onViewDetails: (matchId: number) => void;
  isCurrentlyLinked: boolean;
}

function PlayerDisplay({ player }: { player: MatchedPlayer }) {
  const content = (
    <div className="flex items-center gap-2 py-1 cursor-pointer">
      <Avatar className={cn("h-6 w-6", player.is_captain && "ring-2 ring-yellow-500")}>
        <AvatarImage src={player.avatar || undefined} />
        <AvatarFallback>
          <User className="h-3 w-3" />
        </AvatarFallback>
      </Avatar>
      <span className={cn(
        "text-xs truncate max-w-[100px]",
        player.is_captain ? "text-yellow-500 font-medium" : "text-foreground",
        player.user_id && "hover:underline"
      )}>
        {player.username || `Steam ${player.steam_id}`}
        {player.is_captain && " (C)"}
      </span>
    </div>
  );

  // If player is linked to a user, wrap with popover
  if (player.user_id && player.username) {
    return (
      <UserPopover
        userId={player.user_id}
        username={player.username}
        avatar={player.avatar}
      >
        {content}
      </UserPopover>
    );
  }

  return content;
}

export function SteamMatchCard({
  match,
  onLink,
  onViewDetails,
  isCurrentlyLinked,
}: SteamMatchCardProps) {
  const date = new Date(match.start_time * 1000);
  const formattedDate = date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
  const formattedTime = date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  });
  const durationMinutes = Math.floor(match.duration / 60);

  return (
    <div
      className={cn(
        'border rounded-lg p-4',
        isCurrentlyLinked && 'ring-2 ring-primary'
      )}
      data-testid="match-card"
    >
      {/* Header */}
      <div className="flex justify-between items-start mb-3">
        <div>
          <p className="font-medium">Match #{match.match_id}</p>
          <p className="text-xs text-muted-foreground">
            {formattedDate} &bull; {formattedTime} &bull; {durationMinutes}m
          </p>
        </div>
        <span className="text-xs text-muted-foreground">
          {match.player_overlap} players
        </span>
      </div>

      {/* Matched Players */}
      <div className="flex justify-between gap-4 py-3">
        {/* Radiant side */}
        <div className="flex-1">
          <p className="text-xs text-green-500 font-medium mb-1">Radiant</p>
          <div className="space-y-0.5">
            {(match.matched_players ?? [])
              .filter(p => p.is_radiant)
              .map(player => (
                <PlayerDisplay key={player.steam_id} player={player} />
              ))}
            {(match.matched_players ?? []).filter(p => p.is_radiant).length === 0 && (
              <span className="text-xs text-muted-foreground">No matches</span>
            )}
          </div>
        </div>

        <span className="text-lg font-bold text-muted-foreground self-center">VS</span>

        {/* Dire side */}
        <div className="flex-1">
          <p className="text-xs text-red-500 font-medium mb-1">Dire</p>
          <div className="space-y-0.5">
            {(match.matched_players ?? [])
              .filter(p => !p.is_radiant)
              .map(player => (
                <PlayerDisplay key={player.steam_id} player={player} />
              ))}
            {(match.matched_players ?? []).filter(p => !p.is_radiant).length === 0 && (
              <span className="text-xs text-muted-foreground">No matches</span>
            )}
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-2 mt-3">
        <Button
          variant="outline"
          size="sm"
          className="flex-1"
          onClick={() => onViewDetails(match.match_id)}
          data-testid="view-details-btn"
        >
          View Details
        </Button>
        <Button
          size="sm"
          className="flex-1"
          onClick={() => onLink(match.match_id)}
          disabled={isCurrentlyLinked}
          data-testid="link-btn"
        >
          {isCurrentlyLinked ? 'Linked' : 'Link'}
        </Button>
      </div>
    </div>
  );
}
