import { PlusCircleIcon } from 'lucide-react';
import { useState } from 'react';
import { DIALOG_CSS } from '~/components/reusable/modal';
import { Button } from '~/components/ui/button';
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
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import type { TournamentClassType } from '../types';
import { TournamentEditForm } from './editForm';

interface Props {}

export const TournamentCreateModal: React.FC<Props> = () => {
  const currentUser: UserType = useUserStore((state) => state.currentUser);
  const [open, setOpen] = useState(false);

  if (!currentUser || (!currentUser.is_staff && !currentUser.is_superuser)) {
    return <></>;
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <DialogTrigger asChild>
              <Button
                size="lg"
                variant="default"
                className={
                  'bg-emerald-600 hover:bg-emerald-500 text-white' +
                  ' shadow-lg shadow-emerald-900/50 border-b-4 border-b-emerald-800' +
                  ' active:border-b-0 active:translate-y-1 transition-all duration-75' +
                  ' hover:shadow-emerald-500/50'
                }
                data-testid="tournament-create-button"
              >
                <PlusCircleIcon className="text-white" />
                Create Tournament
              </Button>
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
