import { Avatar, AvatarFallback, AvatarImage } from '~/components/ui/avatar';
import { Button } from '~/components/ui/button';
import { User } from 'lucide-react';
import { cn } from '~/lib/utils';

export interface CaptainInfo {
  steam_id: number;
  username: string | null;
  avatar: string | null;
  hero_id: number;
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
}

interface SteamMatchCardProps {
  match: MatchSuggestion;
  onLink: (matchId: number) => void;
  onViewDetails: (matchId: number) => void;
  isCurrentlyLinked: boolean;
}

function CaptainDisplay({ captain }: { captain: CaptainInfo | null }) {
  if (!captain) {
    return (
      <div className="flex flex-col items-center">
        <Avatar className="h-10 w-10">
          <AvatarFallback>
            <User className="h-5 w-5" />
          </AvatarFallback>
        </Avatar>
        <span className="text-xs text-muted-foreground mt-1">Unknown</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center">
      <Avatar className="h-10 w-10">
        <AvatarImage src={captain.avatar || undefined} />
        <AvatarFallback>
          <User className="h-5 w-5" />
        </AvatarFallback>
      </Avatar>
      <span className="text-xs text-foreground mt-1 max-w-[80px] truncate">
        {captain.username || captain.steam_id}
      </span>
      <div className="w-6 h-6 mt-1 bg-muted rounded" title={`Hero ID: ${captain.hero_id}`} />
    </div>
  );
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

      {/* Captains */}
      <div className="flex items-center justify-center gap-6 py-3">
        <CaptainDisplay captain={match.radiant_captain} />
        <span className="text-lg font-bold text-muted-foreground">VS</span>
        <CaptainDisplay captain={match.dire_captain} />
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
