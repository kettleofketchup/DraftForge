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
        <>
          This will delete the series <strong>{seriesName}</strong>. Its
          upcoming events and events with signups or roll call open are deleted
          too, along with their Discord events and tournaments. In-progress,
          completed and cancelled events are kept.
        </>
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
