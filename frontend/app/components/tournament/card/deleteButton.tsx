import React, { useState } from 'react';
import { toast } from 'sonner';
import { useShallow } from 'zustand/react/shallow';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { TrashIconButton } from '~/components/ui/buttons';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';

const log = getLogger('deleteButtonTourn');

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';

import { deleteTournament } from '~/components/api/api';
import type { TournamentType } from '../types';

interface PropsRemoveButton {
  tournament: TournamentType;
  disabled?: boolean;
}

export const TournamentRemoveButton: React.FC<PropsRemoveButton> = ({
  tournament,
  disabled,
}) => {
  const [open, setOpen] = useState(false);
  const delTournamentStore = useUserStore(
    useShallow((state) => state.delTournament),
  );
  const isStaff = useUserStore((state) => state.isStaff);

  const handleChange = () => {
    if (!tournament || !tournament.pk) {
      log.error('Tournament not found or not set');
      return;
    }

    toast.promise(deleteTournament(tournament.pk), {
      loading: `Deleting Tournament ${tournament.pk}.`,
      success: (data) => {
        log.debug('Tournament deleted successfully');
        delTournamentStore(tournament);
        setOpen(false);
        return `${tournament.pk} has been deleted`;
      },
      error: (err) => {
        log.error('Failed to delete tournament', err);
        return `${tournament.pk} could not be deleted`;
      },
    });
  };

  if (!isStaff()) return <> </>;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex flex-row items-center gap-4">
            <TrashIconButton
              size="sm"
              disabled={disabled}
              onClick={() => setOpen(true)}
            />
          </div>
        </TooltipTrigger>
        <TooltipContent>
          <p>Delete tournament</p>
        </TooltipContent>
      </Tooltip>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Delete Tournament?"
        description={`This removes tournament ${tournament.pk}`}
        confirmLabel="Confirm Delete"
        variant="destructive"
        onConfirm={handleChange}
      />
    </TooltipProvider>
  );
};
