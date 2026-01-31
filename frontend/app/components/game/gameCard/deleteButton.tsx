import React, { useState } from 'react';
import { refreshTournamentHook } from '~/components/teamdraft/hooks/refreshTournamentHook';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { TrashIconButton } from '~/components/ui/buttons';
import { deleteGameHook } from '../hooks/deleteGameHook';

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';

import { useUserStore } from '~/store/userStore';
import type { GameType } from '../types';

interface PropsRemoveButton {
  game: GameType;
  disabled?: boolean;
}

export const GameRemoveButton: React.FC<PropsRemoveButton> = ({
  game,
  disabled,
}) => {
  const [open, setOpen] = useState(false);
  const tournament = useUserStore((state) => state.tournament);
  const setTournament = useUserStore((state) => state.setTournament);

  const handleChange = async () => {
    await deleteGameHook({ game });
    await refreshTournamentHook({ tournament, setTournament });
    setOpen(false);
  };

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
          <p>Delete Game</p>
        </TooltipContent>
      </Tooltip>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Delete Game?"
        description={`This removes the game ${game.pk}`}
        confirmLabel="Confirm Delete"
        variant="destructive"
        onConfirm={handleChange}
      />
    </TooltipProvider>
  );
};
