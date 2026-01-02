import { PlusCircleIcon } from 'lucide-react';
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
import { GameCreateForm } from './createForm';

interface Props {}

export const GameCreateModal: React.FC<Props> = (props) => {
  const currentUser: UserType = useUserStore((state) => state.currentUser); // Zustand setter
  const users: UserType[] = useUserStore((state) => state.users); // Zustand setter

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
                  Create Game
                </Button>
              </DialogTrigger>
            </TooltipTrigger>
            <TooltipContent>
              <p>Create a new Game </p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Create Game</DialogTitle>
            <DialogDescription>
              Please fill in the details below to create a new game.
            </DialogDescription>
          </DialogHeader>

          <GameCreateForm />
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

export default GameCreateModal;
