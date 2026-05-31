import { ConfirmDialog } from '~/components/ui/dialogs';

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
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Restart Tournament?"
      description="This will delete the current tournament and all its data (teams, matches, bracket), then create a fresh tournament from this event's config. Signups will be reopened. This cannot be undone."
      confirmLabel="Restart Tournament"
      variant="destructive"
      isLoading={loading}
      onConfirm={onConfirm}
    />
  );
}
