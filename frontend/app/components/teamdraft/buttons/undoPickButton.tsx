import { Undo2 } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { undoLastPick } from '~/components/api/api';
import { WarningButton } from '~/components/ui/buttons';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';

const log = getLogger('undoPickButton');

export const UndoPickButton: React.FC = () => {
  const draft = useUserStore((state) => state.draft);
  const curDraftRound = useUserStore((state) => state.curDraftRound);
  const setTournament = useUserStore((state) => state.setTournament);
  const setDraft = useUserStore((state) => state.setDraft);
  const setCurDraftRound = useUserStore((state) => state.setCurDraftRound);
  const setDraftIndex = useUserStore((state) => state.setDraftIndex);
  const isStaff = useUserStore((state) => state.isStaff);
  const [isLoading, setIsLoading] = useState(false);
  const [open, setOpen] = useState(false);

  // Only staff can undo picks
  if (!isStaff()) return null;

  // Only show if the current round has a pick made
  if (!draft?.pk || !curDraftRound?.choice) return null;

  const handleUndo = async () => {
    if (!draft?.pk) return;

    setIsLoading(true);
    try {
      const updatedTournament = await undoLastPick({ draft_pk: draft.pk });

      setTournament(updatedTournament);
      if (updatedTournament.draft) {
        setDraft(updatedTournament.draft);
      }

      // Find the round that was undone (now has no choice)
      const undoneRound = updatedTournament.draft?.draft_rounds?.find(
        (r) => r.pk === updatedTournament.draft?.latest_round
      );

      if (undoneRound) {
        setCurDraftRound(undoneRound);
        const idx = updatedTournament.draft?.draft_rounds?.findIndex(
          (r) => r.pk === undoneRound.pk
        );
        if (idx !== undefined && idx >= 0) {
          setDraftIndex(idx);
        }
      }

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
