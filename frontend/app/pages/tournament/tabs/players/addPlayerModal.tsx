import type { FormEvent } from 'react';
import React from 'react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip'; // Adjust path as needed
import type { UserType } from '~/components/user/types';

interface Props {
  users: UserType[];
  query: string;
  setQuery: React.Dispatch<React.SetStateAction<string>>;
}

import { PlusCircle } from 'lucide-react';

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
import UserCreateModal from '~/components/user/userCard/createModal';
import { useUserStore } from '~/store/userStore';
import { AddPlayerDropdown } from './addPlayerDropdown';
interface Props {
  users: UserType[];

  addedUsers?: UserType[];
  query: string;
  setQuery: React.Dispatch<React.SetStateAction<string>>;
  addPlayerCallback?: (user: UserType) => Promise<void>;
  removePlayerCallback?: (e: FormEvent, user: UserType) => Promise<void>;
}

import { AdminOnlyButton } from '~/components/reusable/adminButton';
import { getLogger } from '~/lib/logger';
const log = getLogger('addPlayerModal');

export const AddPlayerModal: React.FC<Props> = ({
  addedUsers,
  addPlayerCallback,
  removePlayerCallback,
  query,
  setQuery,
}) => {
  // Find all users not already in the tournament
  const currentUser = useUserStore((state) => state.currentUser);
  const isStaff = useUserStore((state) => state.isStaff);

  if (!isStaff()) {
    return (
      <AdminOnlyButton
        buttonTxt=""
        tooltipTxt={'Only Admins can add users to the tournament'}
      />
    ); // Only staff can add players
  }
  return (
    <Dialog>
      <form>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <DialogTrigger asChild>
                <Button
                  size="icon"
                  variant="default"
                  className={
                    'bg-green-950 hover:bg-green-800 text-white' +
                    ' hover:shadow-sm hover:shadow-green-500/50'
                  }
                >
                  <PlusCircle color="white" className="zs" />
                </Button>
              </DialogTrigger>
            </TooltipTrigger>
            <TooltipContent>
              <p>Add users to the tournament </p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <DialogContent
          className={`'min-w-[98vw] h-[70vh] max-h-[75vh] sm:min-w-[20vw] sm:h-[25em] sm:h-max-[30em]'`}
        >
          <DialogHeader>
            <DialogTitle>Add Users to Tournament </DialogTitle>
            <DialogDescription>
              Search for a user to add to the tournament. You can search by name
              or username.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col justify-start align-start items-start content-start w-full gap-4 mb-4">
            <div className="justify-self-start self-start w-full">
              <AddPlayerDropdown
                query={query}
                setQuery={setQuery}
                addPlayerCallback={addPlayerCallback}
                removePlayerCallback={removePlayerCallback}
                addedUsers={addedUsers}
              />
            </div>
          </div>
          <DialogFooter>
            <div className="flex flex-row  gap-x-4 sm:gap-x-8 justify-center align-center items-center w-full">
              <UserCreateModal query={query} setQuery={setQuery} />
              <DialogClose asChild>
                <Button variant="outline">Cancel</Button>
              </DialogClose>
            </div>
          </DialogFooter>
        </DialogContent>
      </form>
    </Dialog>
  );
};
