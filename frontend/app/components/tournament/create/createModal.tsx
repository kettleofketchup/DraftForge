import { ScrollArea } from '@radix-ui/react-scroll-area';
import { PlusCircleIcon } from 'lucide-react';
import { useState } from 'react';
import { DIALOG_CSS, SCROLLAREA_CSS } from '~/components/reusable/modal';
import { Button } from '~/components/ui/button';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '~/components/ui/dialog';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip'; // Adjust path as needed
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import type { TournamentClassType } from '../types';
import { TournamentEditForm } from './editForm';

interface Props {}

export const TournamentCreateModal: React.FC<Props> = (props) => {
  const currentUser: UserType = useUserStore((state) => state.currentUser); // Zustand setter
  const users: UserType[] = useUserStore((state) => state.users); // Zustand setter

  const [form, setForm] = useState<TournamentClassType>(
    {} as TournamentClassType,
  );

  if (!currentUser || (!currentUser.is_staff && !currentUser.is_superuser)) {
    return <></>;
  }
  return (
    <Dialog>
      <form>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <DialogTrigger asChild>
                <Button
                  size="lg"
                  variant="default"
                  className={
                    'bg-green-950 hover:bg-green-800 text-white' +
                    ' hover:shadow-sm hover:shadow-green-500/50'
                  }
                >
                  <PlusCircleIcon color="white" className="" />
                  Create Tournament
                </Button>
              </DialogTrigger>
            </TooltipTrigger>
            <TooltipContent>
              <p>Create a new tournament </p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <DialogContent className={`${DIALOG_CSS}`}>
            <DialogHeader>
              <DialogTitle>Create Tournament</DialogTitle>
              <DialogDescription>
                Please fill in the details below to create a new tournament.
              </DialogDescription>
            </DialogHeader>

            <TournamentEditForm
              tourn={{} as TournamentClassType}
              form={form}
              setForm={setForm}
            />

          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
          </DialogFooter>
        </DialogContent>
      </form>
    </Dialog>
  );
};

export default TournamentCreateModal;
