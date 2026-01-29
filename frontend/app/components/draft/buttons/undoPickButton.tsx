import React, { useMemo, useState } from 'react';
import { Undo2 } from 'lucide-react';
import { toast } from 'sonner';
import { undoLastPick } from '~/components/api/api';
import { WarningButton } from '~/components/ui/buttons';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { useTeamDraftStore } from '~/store/teamDraftStore';
import { useTournamentDataStore } from '~/store/tournamentDataStore';

const log = getLogger('undoPickButton');

export const UndoPickButton: React.FC = () => {
  // Subscribe to specific fields (not entire draft)
  const draftPk = useTeamDraftStore((state) => state.draft?.pk);
  const draftRounds = useTeamDraftStore((state) => state.draft?.draft_rounds);
  const currentRoundIndex = useTeamDraftStore((state) => state.currentRoundIndex);
  const loadDraft = useTeamDraftStore((state) => state.loadDraft);
  const loadAll = useTournamentDataStore((state) => state.loadAll);
  const isStaff = useUserStore((state) => state.isStaff);

  // Derive current round from subscribed state (reactive)
  const curDraftRound = useMemo(() => {
    if (!draftRounds || draftRounds.length === 0) return null;
    return draftRounds[currentRoundIndex] ?? null;
  }, [draftRounds, currentRoundIndex]);
  const [isLoading, setIsLoading] = useState(false);
  const [open, setOpen] = useState(false);

  // Only staff can undo picks
  if (!isStaff()) return null;

  // Only show if the current round has a pick made
  if (!draftPk || !curDraftRound?.choice) return null;

  const handleUndo = async () => {
    if (!draftPk) return;

    setIsLoading(true);
    try {
      await undoLastPick({ draft_pk: draftPk });

      // Refresh data from server
      await Promise.all([loadAll(), loadDraft()]);

      toast.success('Pick undone successfully');
      log.info('Undo successful');
      setOpen(false);
    } catch (error: any) {
      const message = error?.response?.data?.error || 'Failed to undo pick';
      toast.error(message);
      log.error('Undo failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      <WarningButton
        loading={isLoading}
        onClick={() => setOpen(true)}
      >
        <Undo2 className="mr-2 h-4 w-4" />
        Undo
      </WarningButton>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Undo Last Pick?"
        description="This will undo the last pick made in the draft. The player will be returned to the available pool and the round will be reset."
        confirmLabel="Undo Pick"
        variant="warning"
        isLoading={isLoading}
        onConfirm={handleUndo}
      />
    </>
  );
};
