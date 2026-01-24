import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '~/components/ui/dialog';
import { Button } from '~/components/ui/button';
import { Badge } from '~/components/ui/badge';
import { Loader2, Wand2 } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '~/components/api/axios';
import { cn } from '~/lib/utils';

interface Assignment {
  game_id: number;
  game_round: number;
  game_position: number;
  bracket_type: string;
  match_id: number;
  start_time: number;
  start_time_display: string;
  player_overlap: number;
  radiant_team: string | null;
  dire_team: string | null;
  radiant_captain: string | null;
  dire_captain: string | null;
  radiant_game_num: number | null;
  dire_game_num: number | null;
  match_method: string;
}

interface AutoAssignResult {
  assignments: Assignment[];
  linked_count?: number;
  tournament_date: string;
  total_unlinked_games: number;
  total_candidate_matches: number;
  message?: string;
  error?: string;
}

interface AutoAssignModalProps {
  isOpen: boolean;
  onClose: () => void;
  tournamentId: number;
  onAssignComplete: () => void;
}

const bracketTypeLabels: Record<string, string> = {
  winners: 'Winners',
  losers: 'Losers',
  grand_finals: 'Finals',
  swiss: 'Swiss',
};

export function AutoAssignModal({
  isOpen,
  onClose,
  tournamentId,
  onAssignComplete,
}: AutoAssignModalProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [result, setResult] = useState<AutoAssignResult | null>(null);

  const fetchPreview = async () => {
    setIsLoading(true);
    try {
      const response = await api.post('/steam/auto-assign/', {
        tournament_id: tournamentId,
        preview: true,
        min_overlap: 4,
      });
      setResult(response.data);
    } catch (error) {
      console.error('Failed to fetch auto-assign preview:', error);
      toast.error('Failed to fetch auto-assign preview');
    } finally {
      setIsLoading(false);
    }
  };

  const applyAssignments = async () => {
    setIsApplying(true);
    try {
      const response = await api.post('/steam/auto-assign/', {
        tournament_id: tournamentId,
        apply: true,
        min_overlap: 4,
      });
      toast.success(`Linked ${response.data.linked_count} matches`);
      onAssignComplete();
      onClose();
    } catch (error) {
      console.error('Failed to apply auto-assign:', error);
      toast.error('Failed to apply auto-assign. Are you logged in as staff?');
    } finally {
      setIsApplying(false);
    }
  };

  // Fetch preview when modal opens
  const handleOpenChange = (open: boolean) => {
    if (open) {
      fetchPreview();
    } else {
      setResult(null);
      onClose();
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Wand2 className="h-5 w-5" />
            Auto-Assign Steam Matches
          </DialogTitle>
          <DialogDescription>
            Automatically link Steam matches to bracket games based on tournament date, time order,
            and player overlap.
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : result?.error ? (
            <div className="text-center py-8 text-destructive">{result.error}</div>
          ) : result?.message ? (
            <div className="text-center py-8 text-muted-foreground">{result.message}</div>
          ) : result?.assignments.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No matches could be auto-assigned. Try linking matches manually.
            </div>
          ) : result ? (
            <div className="space-y-4">
              {/* Stats */}
              <div className="flex gap-4 text-sm text-muted-foreground border-b pb-3">
                <span>Tournament Date: {result.tournament_date}</span>
                <span>•</span>
                <span>Unlinked Games: {result.total_unlinked_games}</span>
                <span>•</span>
                <span>Candidate Matches: {result.total_candidate_matches}</span>
              </div>

              {/* Assignments */}
              <div className="space-y-2">
                <p className="text-sm font-medium">
                  {result.assignments.length} assignments found:
                </p>
                {result.assignments.map((assignment) => (
                  <div
                    key={assignment.game_id}
                    className="flex items-center justify-between p-3 bg-muted/50 rounded-lg"
                  >
                    <div className="flex flex-col">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-xs">
                          {bracketTypeLabels[assignment.bracket_type] || assignment.bracket_type}
                        </Badge>
                        <span className="text-sm font-medium">
                          Round {assignment.game_round}, Game {assignment.game_position + 1}
                        </span>
                      </div>
                      <span className="text-xs text-muted-foreground mt-1">
                        <span className="text-green-500">
                          {assignment.radiant_captain || assignment.radiant_team || 'TBD'}
                          {assignment.radiant_game_num && ` (#${assignment.radiant_game_num})`}
                        </span>
                        {' vs '}
                        <span className="text-red-500">
                          {assignment.dire_captain || assignment.dire_team || 'TBD'}
                          {assignment.dire_game_num && ` (#${assignment.dire_game_num})`}
                        </span>
                      </span>
                    </div>
                    <div className="flex flex-col items-end">
                      <span className="text-sm">Match #{assignment.match_id}</span>
                      <span className="text-xs text-muted-foreground">
                        {assignment.start_time_display} UTC
                      </span>
                      <div className="flex items-center gap-1 mt-1">
                        <Badge
                          variant="secondary"
                          className={cn(
                            'text-xs',
                            assignment.player_overlap >= 8
                              ? 'bg-green-500/20 text-green-500'
                              : assignment.player_overlap >= 6
                                ? 'bg-blue-500/20 text-blue-500'
                                : 'bg-yellow-500/20 text-yellow-500'
                          )}
                        >
                          {assignment.player_overlap}/10
                        </Badge>
                        <Badge
                          variant="outline"
                          className={cn(
                            'text-xs',
                            assignment.match_method === 'captain_sequence'
                              ? 'border-green-500 text-green-500'
                              : 'border-yellow-500 text-yellow-500'
                          )}
                        >
                          {assignment.match_method === 'captain_sequence' ? 'seq' : 'overlap'}
                        </Badge>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={applyAssignments}
            disabled={isApplying || !result?.assignments.length}
          >
            {isApplying ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Applying...
              </>
            ) : (
              <>
                <Wand2 className="h-4 w-4 mr-2" />
                Apply {result?.assignments.length || 0} Assignments
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
