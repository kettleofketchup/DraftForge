import { useState, useEffect, useMemo } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { Input } from '~/components/ui/input';
import { Button } from '~/components/ui/button';
import { Badge } from '~/components/ui/badge';
import { Search, Unlink, Calendar } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '~/components/api/axios';
import { SteamMatchCard, type MatchSuggestion } from './SteamMatchCard';
import { DotaMatchStatsModal } from './DotaMatchStatsModal';
import type { BracketMatch } from '../types';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';

interface LinkSteamMatchModalProps {
  isOpen: boolean;
  onClose: () => void;
  game: BracketMatch;
  onLinkUpdated: () => void;
}

const TIER_STYLES: Record<string, { bg: string; border: string; text: string }> = {
  all_players: {
    bg: 'bg-green-500/20',
    border: 'border-green-500',
    text: 'text-green-400',
  },
  captains_plus: {
    bg: 'bg-blue-500/20',
    border: 'border-blue-500',
    text: 'text-blue-400',
  },
  captains_only: {
    bg: 'bg-yellow-500/20',
    border: 'border-yellow-500',
    text: 'text-yellow-400',
  },
  partial: {
    bg: 'bg-gray-500/20',
    border: 'border-gray-500',
    text: 'text-gray-400',
  },
};

export function LinkSteamMatchModal({
  isOpen,
  onClose,
  game,
  onLinkUpdated,
}: LinkSteamMatchModalProps) {
  const tournament = useUserStore((state) => state.tournament);
  const [search, setSearch] = useState('');
  const [suggestions, setSuggestions] = useState<MatchSuggestion[]>([]);
  const [linkedMatchId, setLinkedMatchId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [detailsMatchId, setDetailsMatchId] = useState<number | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // Get tournament date for prioritizing matches on that day
  // Use local date string (YYYY-MM-DD) for reliable comparison (avoids UTC timezone shift)
  const tournamentDateLocal = useMemo(() => {
    if (!tournament?.date_played) return null;
    const date = new Date(tournament.date_played);
    // Use local date components to avoid UTC conversion shifting the date
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`; // e.g., "2026-01-18"
  }, [tournament?.date_played]);

  // Fetch suggestions when modal opens or search changes
  useEffect(() => {
    if (!isOpen || !game.gameId) return;

    const fetchSuggestions = async () => {
      setIsLoading(true);
      try {
        const params = search ? `?search=${encodeURIComponent(search)}` : '';
        const response = await api.get(
          `/steam/games/${game.gameId}/match-suggestions/${params}`
        );
        setSuggestions(response.data.suggestions);
        setLinkedMatchId(response.data.linked_match_id);
      } catch (error) {
        console.error('Failed to fetch suggestions:', error);
      } finally {
        setIsLoading(false);
      }
    };

    const debounce = setTimeout(fetchSuggestions, 300);
    return () => clearTimeout(debounce);
  }, [isOpen, game.gameId, search, refreshKey]);

  const handleLink = async (matchId: number) => {
    if (!game.gameId) return;

    try {
      await api.post(`/steam/games/${game.gameId}/link-match/`, {
        match_id: matchId,
      });
      setLinkedMatchId(matchId);
      onLinkUpdated();
      toast.success(`Linked to Match #${matchId}`);
      onClose();
    } catch (error) {
      console.error('Failed to link match:', error);
      toast.error('Failed to link match. Are you logged in as staff?');
    }
  };

  const handleUnlink = async () => {
    if (!game.gameId) return;

    try {
      await api.delete(`/steam/games/${game.gameId}/unlink-match/`);
      setLinkedMatchId(null);
      setRefreshKey((prev) => prev + 1);
      onLinkUpdated();
      toast.success('Match unlinked');
    } catch (error) {
      console.error('Failed to unlink match:', error);
      toast.error('Failed to unlink match. Are you logged in as staff?');
    }
  };

  // Group suggestions by day, then by tier within each day
  const groupedByDay = suggestions.reduce(
    (acc, suggestion) => {
      const date = new Date(suggestion.start_time * 1000);
      // Use local date for comparison key (avoids UTC timezone shift)
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      const dateLocal = `${year}-${month}-${day}`;
      // Use formatted string for display
      const displayLabel = date.toLocaleDateString('en-US', {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
      });
      if (!acc[dateLocal]) {
        acc[dateLocal] = {
          timestamp: suggestion.start_time,
          matches: [],
          displayLabel,
          isTournamentDay: dateLocal === tournamentDateLocal,
        };
      }
      acc[dateLocal].matches.push(suggestion);
      return acc;
    },
    {} as Record<string, { timestamp: number; matches: MatchSuggestion[]; displayLabel: string; isTournamentDay: boolean }>
  );

  // Sort days: tournament day first, then most recent
  const sortedDays = Object.entries(groupedByDay).sort(([keyA, a], [keyB, b]) => {
    // Tournament day always comes first
    if (a.isTournamentDay) return -1;
    if (b.isTournamentDay) return 1;
    // Then sort by timestamp (most recent first)
    return b.timestamp - a.timestamp;
  });

  const tierOrder = ['all_players', 'captains_plus', 'captains_only', 'partial'];

  return (
    <>
      <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
        <DialogContent
          className="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col"
          data-testid="link-steam-match-modal"
        >
          <DialogHeader>
            <DialogTitle>Link Steam Match</DialogTitle>
          </DialogHeader>

          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by Match ID or Captain name..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-10"
              data-testid="match-search-input"
            />
          </div>

          {/* Currently linked */}
          {linkedMatchId && (
            <div
              className="flex items-center justify-between p-3 bg-muted rounded-lg"
              data-testid="currently-linked"
            >
              <span className="text-sm">
                Currently Linked: <strong>Match #{linkedMatchId}</strong>
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={handleUnlink}
                data-testid="unlink-btn"
              >
                <Unlink className="h-4 w-4 mr-1" />
                Unlink
              </Button>
            </div>
          )}

          {/* Suggestions */}
          <div className="flex-1 overflow-y-auto space-y-4">
            {isLoading ? (
              <div className="text-center py-8 text-muted-foreground">
                Loading suggestions...
              </div>
            ) : suggestions.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                No matches found
              </div>
            ) : (
              sortedDays.map(([dateKey, { matches: dayMatches, displayLabel, isTournamentDay }]) => {
                // Group this day's matches by tier
                const tierGroups = dayMatches.reduce(
                  (acc, match) => {
                    if (!acc[match.tier]) acc[match.tier] = [];
                    acc[match.tier].push(match);
                    return acc;
                  },
                  {} as Record<string, MatchSuggestion[]>
                );

                return (
                  <div key={dateKey} className="space-y-2">
                    {/* Day header */}
                    <div className={cn(
                      "sticky top-0 backdrop-blur py-2 border-b flex items-center gap-2",
                      isTournamentDay ? "bg-primary/10" : "bg-background/95"
                    )}>
                      <span className={cn(
                        "text-sm font-semibold",
                        isTournamentDay ? "text-primary" : "text-foreground"
                      )}>
                        {displayLabel}
                      </span>
                      {isTournamentDay && (
                        <Badge variant="default" className="text-xs py-0">
                          <Calendar className="h-3 w-3 mr-1" />
                          Tournament Day
                        </Badge>
                      )}
                      <span className="text-xs text-muted-foreground">
                        ({dayMatches.length} match{dayMatches.length !== 1 ? 'es' : ''})
                      </span>
                    </div>

                    {/* Tier groups within this day */}
                    {tierOrder.map((tier) => {
                      const tierSuggestions = tierGroups[tier];
                      if (!tierSuggestions?.length) return null;

                      // Sort matches within tier by start_time (most recent first)
                      const sortedTierSuggestions = [...tierSuggestions].sort(
                        (a, b) => b.start_time - a.start_time
                      );

                      const styles = TIER_STYLES[tier];
                      const tierLabel =
                        sortedTierSuggestions[0]?.tier_display || tier.replace('_', ' ');

                      return (
                        <div key={`${dateKey}-${tier}`} data-testid={`tier-${tier}`}>
                          <div
                            className={cn(
                              'px-3 py-1 rounded-t-lg border-b text-xs',
                              styles.bg,
                              styles.border,
                              styles.text
                            )}
                          >
                            <span className="font-medium">{tierLabel}</span>
                          </div>
                          <div className="space-y-2 p-2 border border-t-0 rounded-b-lg">
                            {sortedTierSuggestions.map((suggestion) => (
                              <SteamMatchCard
                                key={suggestion.match_id}
                                match={suggestion}
                                onLink={handleLink}
                                onViewDetails={setDetailsMatchId}
                                isCurrentlyLinked={
                                  linkedMatchId === suggestion.match_id
                                }
                              />
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                );
              })
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Details modal */}
      <DotaMatchStatsModal
        open={detailsMatchId !== null}
        onClose={() => setDetailsMatchId(null)}
        matchId={detailsMatchId}
      />
    </>
  );
}
