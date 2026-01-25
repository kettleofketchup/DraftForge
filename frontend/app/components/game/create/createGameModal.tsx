import { PlusCircleIcon } from 'lucide-react';
import { useState } from 'react';
import { Button } from '~/components/ui/button';
import { FormDialog } from '~/components/ui/dialogs';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';

import { useUserStore } from '~/store/userStore';
import { GameCreateForm } from './createForm';

interface Props {}

export const GameCreateModal: React.FC<Props> = (props) => {
  const currentUser: UserType = useUserStore((state) => state.currentUser);
  const [open, setOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    // Form submission is handled by GameCreateForm internally
    // This is a placeholder for proper form integration
  };

  if (!currentUser || (!currentUser.is_staff && !currentUser.is_superuser)) {
    return <></>;
  }

  return (
    <>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="lg"
              variant="default"
              className={
                'bg-emerald-600 hover:bg-emerald-500 text-white' +
                ' shadow-lg shadow-emerald-900/50 border-b-4 border-b-emerald-800' +
                ' active:border-b-0 active:translate-y-1 transition-all duration-75' +
                ' hover:shadow-emerald-500/50'
              }
              onClick={() => setOpen(true)}
            >
              <PlusCircleIcon className="text-white" />
              Create Game
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>Create a new Game</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <FormDialog
        open={open}
        onOpenChange={setOpen}
        title="Create Game"
        description="Please fill in the details below to create a new game."
        submitLabel="Create"
        isSubmitting={isSubmitting}
        onSubmit={handleSubmit}
        size="lg"
        showFooter={false}
      >
        <GameCreateForm />
      </FormDialog>
    </>
  );
};

export default GameCreateModal;
