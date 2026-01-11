import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { Input } from '~/components/ui/input';
import { Button } from '~/components/ui/button';
import { Search, Unlink } from 'lucide-react';
import { api } from '~/components/api/axios';
import { SteamMatchCard, type MatchSuggestion } from './SteamMatchCard';
import { DotaMatchStatsModal } from './DotaMatchStatsModal';
import type { BracketMatch } from '../types';
import { cn } from '~/lib/utils';

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
  const [search, setSearch] = useState('');
  const [suggestions, setSuggestions] = useState<MatchSuggestion[]>([]);
  const [linkedMatchId, setLinkedMatchId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [detailsMatchId, setDetailsMatchId] = useState<number | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

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
      onClose();
    } catch (error) {
      console.error('Failed to link match:', error);
    }
  };

  const handleUnlink = async () => {
    if (!game.gameId) return;

    try {
      await api.delete(`/steam/games/${game.gameId}/unlink-match/`);
      setLinkedMatchId(null);
      setRefreshKey((prev) => prev + 1);
      onLinkUpdated();
    } catch (error) {
      console.error('Failed to unlink match:', error);
    }
  };

  // Group suggestions by tier
  const groupedSuggestions = suggestions.reduce(
    (acc, suggestion) => {
      const tier = suggestion.tier;
      if (!acc[tier]) acc[tier] = [];
      acc[tier].push(suggestion);
      return acc;
    },
    {} as Record<string, MatchSuggestion[]>
  );

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
              tierOrder.map((tier) => {
                const tierSuggestions = groupedSuggestions[tier];
                if (!tierSuggestions?.length) return null;

                const styles = TIER_STYLES[tier];
                const tierLabel =
                  tierSuggestions[0]?.tier_display || tier.replace('_', ' ');

                return (
                  <div key={tier} data-testid={`tier-${tier}`}>
                    <div
                      className={cn(
                        'px-3 py-1.5 rounded-t-lg border-b',
                        styles.bg,
                        styles.border,
                        styles.text
                      )}
                    >
                      <span className="text-sm font-medium">{tierLabel}</span>
                    </div>
                    <div className="space-y-2 p-2 border border-t-0 rounded-b-lg">
                      {tierSuggestions.map((suggestion) => (
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
