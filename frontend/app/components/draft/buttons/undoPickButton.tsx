import { Undo2 } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { undoLastPick } from '~/components/api/api';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '~/components/ui/alert-dialog';
import { Button } from '~/components/ui/button';
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
      setDraft(updatedTournament.draft);

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
    } catch (error: any) {
      const message = error?.response?.data?.error || 'Failed to undo pick';
      toast.error(message);
      log.error('Undo failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          variant="outline"
          className="bg-orange-900/50 border-orange-600 text-orange-400 hover:bg-orange-800/50"
          disabled={isLoading}
        >
          <Undo2 className="mr-2 h-4 w-4" />
          Undo
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Undo Last Pick?</AlertDialogTitle>
          <AlertDialogDescription>
            This will undo the last pick made in the draft. The player will be
            returned to the available pool and the round will be reset.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleUndo}
            className="bg-orange-600 hover:bg-orange-700"
          >
            Undo Pick
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
};
