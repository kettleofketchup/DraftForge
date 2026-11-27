import { useMutationState, useQueryClient } from '@tanstack/react-query';
import { BarChart3, Link2, Loader2, RotateCcw, Swords } from 'lucide-react';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { toast } from 'sonner';
import { LobbyPanel } from '~/components/lobby/LobbyPanel';
import { provisionalWinnerSlot } from '~/components/lobby/provisional';
import { AdminOnlyButton } from '~/components/reusable/adminButton';
import type { TeamType } from '~/components/tournament/types';
import { Badge } from '~/components/ui/badge';
import { PrimaryButton, SecondaryButton } from '~/components/ui/buttons';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import {
  MATCH_RESULT_MUTATION_KEY,
  usePersistMatchResult,
} from '~/hooks/useBracket';
import { useCanManageCurrentTournament } from '~/hooks/useCanManageTournament';
import { useGameLobby } from '~/hooks/useGameLobby';
import { useCreateHeroDraft, useResetHeroDraft } from '~/hooks/useHeroDraft';
import { cn } from '~/lib/utils';
import { useBracketStore } from '~/store/bracketStore';
import { useUserStore } from '~/store/userStore';
import type { BracketMatch } from '../types';
import { DotaMatchStatsModal } from './DotaMatchStatsModal';
import { LinkSteamMatchModal } from './LinkSteamMatchModal';

interface MatchStatsModalProps {
  match: BracketMatch | null;
  isOpen: boolean;
  onClose: () => void;
  initialDraftId?: number | null;
  onOpenHeroDraft?: (draftId: number) => void;
  embedded?: boolean;
  openableDraftIds?: ReadonlySet<number>;
}

export function MatchStatsModal({
  match: matchProp,
  isOpen,
  onClose,
  initialDraftId,
  onOpenHeroDraft,
  embedded = false,
  openableDraftIds,
}: MatchStatsModalProps) {
  const navigate = useNavigate();
  const { pk } = useParams<{ pk: string }>();
  const currentUser = useUserStore((state) => state.currentUser);
  const tournament = useUserStore((state) => state.tournament);
  const canManage = useCanManageCurrentTournament();

  // Subscribe to match directly from store for reactive updates
  const storeMatch = useBracketStore((state) =>
    matchProp ? state.matches.find((m) => m.id === matchProp.id) : null,
  );
  // Use store match if available (has latest state), otherwise fall back to prop
  const match = storeMatch ?? matchProp;

  const setMatchWinner = useBracketStore((state) => state.setMatchWinner);
  const advanceWinner = useBracketStore((state) => state.advanceWinner);
  const unsetMatchWinner = useBracketStore((state) => state.unsetMatchWinner);
  const holdResultForSave = useBracketStore((state) => state.holdResultForSave);
  const queryClient = useQueryClient();
  const persistMatchResult = usePersistMatchResult(tournament?.pk ?? undefined);
  const savingGameIds = useMutationState({
    filters: { mutationKey: MATCH_RESULT_MUTATION_KEY, status: 'pending' },
    select: (m) =>
      (m.state.variables as { gameId?: number } | undefined)?.gameId,
  });

  const [showStatsModal, setShowStatsModal] = useState(false);
  const [showLinkModal, setShowLinkModal] = useState(false);
  const [showResetConfirm, setShowResetConfirm] = useState(false);

  const createDraftMutation = useCreateHeroDraft();
  const resetDraftMutation = useResetHeroDraft();

  // The lobby's provisional result pre-selects (never submits) a winner.
  const { data: lobbyData } = useGameLobby(
    match?.gameId,
    isOpen && !!currentUser && !embedded,
  );

  if (!match) return null;

  const lobbyWinnerSlot =
    match.status !== 'completed'
      ? provisionalWinnerSlot(
          lobbyData?.lobby,
          match.radiantTeam?.pk,
          match.direTeam?.pk,
        )
      : null;

  const resultSaving = savingGameIds.includes(match.gameId);
  const isGameComplete = match.status === 'completed';
  const hasMatchId = !!match.steamMatchId;

  // A saved bracket with no structural edits persists the result straight
  // away; otherwise the server's teams may differ, so it rides the next Save.
  const canPersistResult = () =>
    !!match.gameId && !useBracketStore.getState().hasStructuralEdits;

  const handleSetWinner = (winner: 'radiant' | 'dire') => {
    const persist = canPersistResult();
    setMatchWinner(match.id, winner);
    advanceWinner(match.id);
    if (persist && match.gameId) {
      persistMatchResult.mutate({ gameId: match.gameId, winner });
    } else {
      holdResultForSave();
    }
  };

  const handleUnsetWinner = () => {
    const persist = canPersistResult();
    unsetMatchWinner(match.id);
    if (persist && match.gameId) {
      persistMatchResult.mutate({ gameId: match.gameId, winner: null });
    } else {
      holdResultForSave();
    }
  };

  const handleLinkUpdated = () => {
    if (tournament?.pk) {
      queryClient.invalidateQueries({ queryKey: ['bracket', tournament.pk] });
    }
  };

  const handleResetDraft = async () => {
    if (!match.herodraft_id) return;

    try {
      await resetDraftMutation.mutateAsync(match.herodraft_id);
      toast.success('Draft reset successfully');
      setShowResetConfirm(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      toast.error(`Failed to reset draft: ${message}`);
    }
  };

  const handleOpenDraft = async () => {
    if (!pk || !onOpenHeroDraft) {
      toast.error('Unable to open draft', {
        description: 'Missing tournament context',
      });
      return;
    }

    let draftIdToOpen: number;

    if (match.herodraft_id) {
      // Draft already exists, just open it
      draftIdToOpen = match.herodraft_id;
    } else if (match.gameId) {
      // Create new draft (backend is idempotent - returns existing if race condition)
      // Pass team IDs so backend can assign them if not already set
      try {
        const draft = await createDraftMutation.mutateAsync({
          gameId: match.gameId,
          options: {
            radiantTeamId: match.radiantTeam?.pk,
            direTeamId: match.direTeam?.pk,
          },
        });
        draftIdToOpen = draft.id;
        toast.success('Draft created!');

        // Reload bracket to update herodraft_id in the match
        if (tournament?.pk) {
          queryClient.invalidateQueries({
            queryKey: ['bracket', tournament.pk],
          });
        }
      } catch (error) {
        const message =
          error instanceof Error ? error.message : 'Unknown error';
        toast.error(`Failed to create draft: ${message}`);
        return;
      }
    } else {
      toast.error('Save the bracket first', {
        description: 'Game records are created when you save the bracket.',
      });
      return;
    }

    // Navigate directly to the herodraft page
    navigate(`/herodraft/${draftIdToOpen}`);
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      {/* Never taller than the viewport (the lobby panel makes it long): the
          header and close button stay put and the body scrolls. dvh follows
          the mobile browser bars; vh is the fallback. */}
      <DialogContent
        className={cn(
          'max-w-2xl flex flex-col gap-4 overflow-hidden',
          'max-h-[calc(100vh-2rem)]',
          'supports-[height:100dvh]:max-h-[calc(100dvh-2rem-env(safe-area-inset-top)-env(safe-area-inset-bottom))]',
        )}
        data-testid="matchStatsModal"
      >
        <DialogHeader className="shrink-0 pr-8">
          <DialogTitle data-testid="match-details-header">
            Match Details
          </DialogTitle>
          <DialogDescription>
            {match.bracketType === 'grand_finals'
              ? 'Grand Finals'
              : `${match.bracketType === 'winners' ? 'Winners' : 'Losers'} Round ${match.round}`}
          </DialogDescription>
        </DialogHeader>

        <div
          className="-mx-6 min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-6 pb-1"
          data-testid="matchStatsModal-body"
        >
          {/* Teams display — auto-sized middle column so the VS / Final badge
              doesn't eat 1/3 of the iPhone-SE-width modal and squeeze the
              team names into overlap. */}
          <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] gap-2 items-center py-3 sm:gap-4 sm:py-4">
            {/* Stored as "radiant", but captains pick sides at draft time, so
                the labels stay neutral. */}
            <TeamCard
              team={match.radiantTeam}
              score={match.radiantScore}
              isWinner={match.winner === 'radiant'}
              label="Team 1"
            />

            {/* VS divider */}
            <div className="flex flex-col items-center gap-1 text-center shrink-0">
              <span className="text-lg sm:text-2xl font-bold text-muted-foreground">
                VS
              </span>
              {match.status === 'completed' && (
                <Badge variant="outline" data-testid="match-status-final">
                  Final
                </Badge>
              )}
              {match.status === 'live' && (
                <Badge className="bg-live" data-testid="match-status-live">
                  LIVE
                </Badge>
              )}
            </div>

            {/* Team 2 (stored as "dire") */}
            <TeamCard
              team={match.direTeam}
              score={match.direScore}
              isWinner={match.winner === 'dire'}
              label="Team 2"
            />
          </div>

          {/* Staff controls */}
          {!embedded &&
            canManage &&
            match.status !== 'completed' &&
            match.radiantTeam &&
            match.direTeam && (
              <div className="border-t pt-4">
                <p className="text-sm text-muted-foreground mb-2">
                  Set Winner:
                </p>
                <div className="flex gap-2">
                  <SecondaryButton
                    className={cn(
                      'flex-1',
                      lobbyWinnerSlot === 'radiant' && 'ring-2 ring-warning',
                    )}
                    onClick={() => handleSetWinner('radiant')}
                    disabled={resultSaving}
                    data-testid="radiantWinsButton"
                    data-lobby-suggested={
                      lobbyWinnerSlot === 'radiant' || undefined
                    }
                  >
                    {match.radiantTeam.captain
                      ? DisplayName(match.radiantTeam.captain)
                      : match.radiantTeam.name}{' '}
                    Wins
                    {lobbyWinnerSlot === 'radiant' && ' (lobby result)'}
                  </SecondaryButton>
                  <SecondaryButton
                    className={cn(
                      'flex-1',
                      lobbyWinnerSlot === 'dire' && 'ring-2 ring-warning',
                    )}
                    onClick={() => handleSetWinner('dire')}
                    disabled={resultSaving}
                    data-testid="direWinsButton"
                    data-lobby-suggested={
                      lobbyWinnerSlot === 'dire' || undefined
                    }
                  >
                    {match.direTeam.captain
                      ? DisplayName(match.direTeam.captain)
                      : match.direTeam.name}{' '}
                    Wins
                    {lobbyWinnerSlot === 'dire' && ' (lobby result)'}
                  </SecondaryButton>
                </div>
              </div>
            )}

          {/* Unset Winner — show whenever the row is "set", even if the
              derived winner is missing. A match can land in status=completed
              with winner=undefined when the backend's winning_team FK
              doesn't match either current radiant_team / dire_team (e.g. a
              prior team change broke the derivation in bracketStore.ts), and
              admins need a recovery path. */}
          {!embedded &&
            canManage &&
            (match.status === 'completed' || match.winner) && (
              <div className="border-t pt-4">
                <SecondaryButton
                  size="sm"
                  onClick={handleUnsetWinner}
                  disabled={resultSaving}
                  data-testid="unsetWinnerButton"
                >
                  <RotateCcw className="size-4 mr-1" />
                  Unset Winner
                </SecondaryButton>
              </div>
            )}

          {embedded &&
            match.herodraft_id != null &&
            openableDraftIds?.has(match.herodraft_id) && (
              <div className="border-t pt-4">
                <PrimaryButton
                  size="sm"
                  onClick={() => onOpenHeroDraft?.(match.herodraft_id!)}
                  data-testid="view-draft-btn"
                >
                  <Swords className="size-4 mr-1" />
                  View Draft
                </PrimaryButton>
              </div>
            )}

          {/* Hero Draft button - show for staff or captains */}
          {!embedded &&
            match.radiantTeam &&
            match.direTeam &&
            (() => {
              const isCaptain =
                match.radiantTeam?.captain?.pk === currentUser?.pk ||
                match.direTeam?.captain?.pk === currentUser?.pk;

              const canAccessDraft = canManage || isCaptain;

              // If draft exists, anyone can view it
              // If draft doesn't exist, only staff/captain can start it
              const canStartOrViewDraft = match.herodraft_id || canAccessDraft;

              if (!canStartOrViewDraft) {
                return (
                  <div className="border-t pt-4">
                    <AdminOnlyButton
                      buttonTxt="Start Draft"
                      tooltipTxt="You must be a staff member or captain to start a draft."
                    />
                  </div>
                );
              }

              // Check if game exists (bracket has been saved)
              const gameNotSaved = !match.herodraft_id && !match.gameId;

              return (
                <div className="border-t pt-4">
                  <div className="flex flex-col gap-2">
                    <div className="flex gap-2 flex-wrap">
                      <PrimaryButton
                        size="sm"
                        onClick={handleOpenDraft}
                        disabled={createDraftMutation.isPending || gameNotSaved}
                        title={
                          gameNotSaved
                            ? 'Save the bracket first to create games'
                            : undefined
                        }
                        data-testid="view-draft-btn"
                      >
                        {createDraftMutation.isPending ? (
                          <Loader2 className="size-4 mr-1 animate-spin" />
                        ) : (
                          <Swords className="size-4 mr-1" />
                        )}
                        {match.herodraft_id ? 'View Draft' : 'Start Draft'}
                      </PrimaryButton>
                      {canManage && match.herodraft_id && (
                        <SecondaryButton
                          size="sm"
                          onClick={() => setShowResetConfirm(true)}
                          disabled={resetDraftMutation.isPending}
                          data-testid="reset-draft-btn"
                        >
                          {resetDraftMutation.isPending ? (
                            <Loader2 className="size-4 mr-1 animate-spin" />
                          ) : (
                            <RotateCcw className="size-4 mr-1" />
                          )}
                          Restart Draft
                        </SecondaryButton>
                      )}
                    </div>
                    {gameNotSaved && (
                      <p className="text-xs text-muted-foreground">
                        Save the bracket first to create game records before
                        starting a draft.
                      </p>
                    )}
                  </div>
                </div>
              );
            })()}

          {/* dota_lobby in-game lobby (signed-in users; the API needs a login) */}
          {!embedded && match.gameId && currentUser && (
            <LobbyPanel gameId={match.gameId} />
          )}

          {/* Steam match info and Stats button */}
          {hasMatchId && (
            <div className="border-t pt-4">
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  Steam Match ID: {match.steamMatchId}
                </p>
                {isGameComplete && (
                  <SecondaryButton
                    size="sm"
                    onClick={() => setShowStatsModal(true)}
                  >
                    <BarChart3 className="size-4 mr-1" />
                    View Stats
                  </SecondaryButton>
                )}
              </div>
            </div>
          )}

          {/* Staff: Link Steam Match button */}
          {canManage && !embedded && (
            <div className="border-t pt-4">
              <SecondaryButton
                size="sm"
                onClick={() => setShowLinkModal(true)}
                data-testid="link-steam-match-btn"
              >
                <Link2 className="size-4 mr-1" />
                {match.steamMatchId
                  ? `Linked: Match #${match.steamMatchId}`
                  : 'Link Steam Match'}
              </SecondaryButton>
            </div>
          )}
        </div>

        {/* Detailed Match Stats Modal */}
        <DotaMatchStatsModal
          open={showStatsModal}
          onClose={() => setShowStatsModal(false)}
          matchId={match.steamMatchId ?? null}
          embedded={embedded}
        />

        {/* Link Steam Match Modal */}
        <LinkSteamMatchModal
          isOpen={showLinkModal}
          onClose={() => setShowLinkModal(false)}
          game={match}
          onLinkUpdated={handleLinkUpdated}
        />

        {/* Reset Draft Confirmation Dialog */}
        <ConfirmDialog
          open={showResetConfirm}
          onOpenChange={setShowResetConfirm}
          title="Reset Hero Draft?"
          description="This will reset the draft to its initial state. All picks, bans, and roll results will be cleared. Both captains will need to ready up again."
          confirmLabel="Reset Draft"
          variant="destructive"
          onConfirm={handleResetDraft}
        />
      </DialogContent>
    </Dialog>
  );
}

interface TeamCardProps {
  team?: Pick<TeamType, 'name' | 'captain'>;
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

  const displayName = team.captain ? DisplayName(team.captain) : team.name;

  return (
    <div
      className={cn(
        'text-center p-3 sm:p-4 rounded-lg min-w-0',
        isWinner ? 'bg-success/10 ring-2 ring-success' : 'bg-muted/50',
      )}
    >
      <UserAvatar
        user={team.captain}
        fallbackName={team.name}
        size="lg"
        className="sm:h-12 sm:w-12 mb-2"
      />
      <p
        className={cn(
          'font-medium text-sm sm:text-base truncate',
          isWinner && 'text-success',
        )}
        title={displayName}
      >
        {displayName}
      </p>
      <p className="text-xs text-muted-foreground">{label}</p>
      {score !== undefined && (
        <p
          className={cn('text-2xl font-bold mt-1', isWinner && 'text-success')}
        >
          {score}
        </p>
      )}
      {isWinner && (
        <span className="text-xs sm:text-sm text-success">Winner</span>
      )}
    </div>
  );
}
