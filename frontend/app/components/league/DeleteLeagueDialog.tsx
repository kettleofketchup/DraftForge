import { toast } from 'sonner';

import { DeleteDialog } from '~/components/ui/dialogs';
import { extractApiError } from '~/lib/apiError';
import { useDeleteLeagueMutation } from './hooks/useDeleteLeagueMutation';
import type { LeagueType } from './schemas';

interface DeleteLeagueDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  league: LeagueType;
  onDeleted?: () => void;
}

export function DeleteLeagueDialog({
  open,
  onOpenChange,
  league,
  onDeleted,
}: DeleteLeagueDialogProps) {
  const deleteMutation = useDeleteLeagueMutation(league.pk ?? 0);

  async function handleDelete() {
    if (league.pk == null) return;
    try {
      await deleteMutation.mutateAsync();
      toast.success(`League "${league.name}" deleted`);
      onOpenChange(false);
      onDeleted?.();
    } catch (err) {
      const message =
        extractApiError(err) ??
        (err instanceof Error ? err.message : 'Failed to delete league');
      toast.error(message);
    }
  }

  return (
    <DeleteDialog
      open={open}
      onOpenChange={onOpenChange}
      entityKind="League"
      entityName={league.name}
      description={
        <>
          This will permanently delete <strong>{league.name}</strong> and cannot be undone.
          Tournaments, matches, and members associated with this league will lose their
          league reference.
        </>
      }
      isLoading={deleteMutation.isPending}
      onConfirm={handleDelete}
      contentTestId="delete-league-dialog"
      inputTestId="delete-league-confirm-input"
      cancelTestId="delete-league-cancel"
      confirmTestId="delete-league-confirm"
    />
  );
}
