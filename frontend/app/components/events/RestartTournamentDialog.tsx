import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '~/components/ui/alert-dialog';
import { CancelButton, ConfirmButton } from '~/components/ui/buttons';

interface RestartTournamentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  loading?: boolean;
}

export function RestartTournamentDialog({
  open,
  onOpenChange,
  onConfirm,
  loading,
}: RestartTournamentDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="bg-red-950/95 border-red-800">
        <AlertDialogHeader>
          <AlertDialogTitle>Restart Tournament?</AlertDialogTitle>
          <AlertDialogDescription className="text-slate-300">
            This will delete the current tournament and all its data (teams, matches, bracket),
            then create a fresh tournament from this event's config. Signups will be reopened.
            This cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter className="gap-2">
          <CancelButton onClick={() => onOpenChange(false)} disabled={loading}>
            Cancel
          </CancelButton>
          <ConfirmButton
            variant="destructive"
            onClick={onConfirm}
            loading={loading}
          >
            Restart Tournament
          </ConfirmButton>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
