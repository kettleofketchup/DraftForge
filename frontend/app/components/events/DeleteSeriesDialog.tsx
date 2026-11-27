import { DeleteDialog } from '~/components/ui/dialogs';

interface DeleteSeriesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  seriesName: string;
  isLoading?: boolean;
  onConfirm: () => void | Promise<void>;
}

export function DeleteSeriesDialog({
  open,
  onOpenChange,
  seriesName,
  isLoading = false,
  onConfirm,
}: DeleteSeriesDialogProps) {
  return (
    <DeleteDialog
      open={open}
      onOpenChange={onOpenChange}
      entityKind="Event Series"
      entityName={seriesName}
      description={
        <div className="space-y-2">
          <div>
            This will delete the series <strong>{seriesName}</strong>.
          </div>
          <div>
            Upcoming, signups-open and roll-call occurrences with sign-ups or
            historical signup records are cancelled and kept. Empty upcoming,
            signups-open and roll-call occurrences are deleted, along with their
            Discord scheduled events and tournaments.
          </div>
          <div>
            In-progress, completed and already-cancelled occurrences are kept.
          </div>
        </div>
      }
      isLoading={isLoading}
      onConfirm={onConfirm}
      contentTestId="delete-series-dialog"
      inputTestId="delete-series-confirm-input"
      confirmTestId="delete-series-confirm"
      cancelTestId="delete-series-cancel"
    />
  );
}
