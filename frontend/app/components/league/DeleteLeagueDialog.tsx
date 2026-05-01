import { useEffect, useState } from 'react';
import { toast } from 'sonner';

import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '~/components/ui/alert-dialog';
import { CancelButton, ConfirmButton } from '~/components/ui/buttons';
import { Input } from '~/components/ui/input';
import { Label } from '~/components/ui/label';
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
  const [confirmName, setConfirmName] = useState('');
  const deleteMutation = useDeleteLeagueMutation(league.pk ?? 0);

  useEffect(() => {
    if (!open) setConfirmName('');
  }, [open]);

  const nameMatches = confirmName === league.name;
  const isDeleting = deleteMutation.isPending;
  const canDelete = nameMatches && !isDeleting && league.pk != null;

  async function handleDelete() {
    if (!canDelete) return;
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
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent
        className="max-w-[calc(100%-2rem)] sm:max-w-md bg-red-950/95 border-red-800"
        data-testid="delete-league-dialog"
      >
        <AlertDialogHeader>
          <AlertDialogTitle>Delete League?</AlertDialogTitle>
          <AlertDialogDescription className="text-slate-300 space-y-2">
            <span className="block">
              This will permanently delete <strong>{league.name}</strong> and cannot
              be undone. Tournaments, matches, and members associated with this
              league will lose their league reference.
            </span>
            <span className="block">
              Type the league name <strong>{league.name}</strong> to confirm.
            </span>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div className="space-y-2">
          <Label htmlFor="delete-league-confirm-input">League name</Label>
          <Input
            id="delete-league-confirm-input"
            data-testid="delete-league-confirm-input"
            value={confirmName}
            onChange={(e) => setConfirmName(e.target.value)}
            placeholder={league.name}
            autoComplete="off"
            disabled={isDeleting}
          />
        </div>
        <AlertDialogFooter className="flex-col-reverse sm:flex-row gap-3">
          <CancelButton
            onClick={() => onOpenChange(false)}
            disabled={isDeleting}
            data-testid="delete-league-cancel"
          >
            Cancel
          </CancelButton>
          <ConfirmButton
            onClick={handleDelete}
            loading={isDeleting}
            variant="destructive"
            disabled={!canDelete}
            data-testid="delete-league-confirm"
          >
            Delete League
          </ConfirmButton>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
