import { PlusCircleIcon } from 'lucide-react';
import { useState } from 'react';
import { PrimaryButton } from '~/components/ui/buttons';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { canCreateTournament } from '~/lib/tournamentPermissions';
import { useUserStore } from '~/store/userStore';
import type { TournamentClassType } from '../types';
import { TournamentEditForm } from './editForm';

interface Props {}

export const TournamentCreateModal: React.FC<Props> = () => {
  const currentUser = useUserStore((state) => state.currentUser);
  // Matches IsStaff on /api/tournament/register.
  const canCreate = canCreateTournament(currentUser);
  const [open, setOpen] = useState(false);

  if (!canCreate) {
    return <></>;
  }

  return (
    <>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <PrimaryButton
              size="lg"
              data-testid="tournament-create-button"
              onClick={() => setOpen(true)}
            >
              <PlusCircleIcon className="text-white" />
              Create Tournament
            </PrimaryButton>
          </TooltipTrigger>
          <TooltipContent>
            <p>Create a new tournament</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <TournamentEditForm
        tourn={{} as TournamentClassType}
        open={open}
        onOpenChange={setOpen}
        title="Create Tournament"
        description="Please fill in the details below to create a new tournament."
        onSuccess={() => setOpen(false)}
        data-testid="tournament-create-modal"
      />
    </>
  );
};

export default TournamentCreateModal;
