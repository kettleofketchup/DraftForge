import { PlusCircleIcon } from 'lucide-react';
import { useState } from 'react';
import { DIALOG_CSS } from '~/components/reusable/modal';
import { PrimaryButton } from '~/components/ui/buttons';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '~/components/ui/dialog';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { useCanCreateAnyTournament } from '~/hooks/usePermissions';
import type { TournamentClassType } from '../types';
import { TournamentEditForm } from './editForm';

interface Props {}

export const TournamentCreateModal: React.FC<Props> = () => {
  const canCreate = useCanCreateAnyTournament();
  const [open, setOpen] = useState(false);

  // Mirror the backend's per-league admin cascade: site admin, or admin
  // of any organisation, or admin of any league. Keeps the button from
  // showing to users the backend would reject on submit.
  if (!canCreate) {
    return <></>;
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <DialogTrigger asChild>
              <PrimaryButton
                size="lg"
                data-testid="tournament-create-button"
              >
                <PlusCircleIcon className="text-white" />
                Create Tournament
              </PrimaryButton>
            </DialogTrigger>
          </TooltipTrigger>
          <TooltipContent>
            <p>Create a new tournament</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <DialogContent className={DIALOG_CSS} data-testid="tournament-create-modal">
        <DialogHeader>
          <DialogTitle>Create Tournament</DialogTitle>
          <DialogDescription>
            Please fill in the details below to create a new tournament.
          </DialogDescription>
        </DialogHeader>

        <TournamentEditForm
          tourn={{} as TournamentClassType}
          onSuccess={() => setOpen(false)}
        />
      </DialogContent>
    </Dialog>
  );
};

export default TournamentCreateModal;
