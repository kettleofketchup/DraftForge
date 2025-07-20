import type { FormEvent } from 'react';
import React, { useEffect } from 'react';
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
import { Label } from '~/components/ui/label';
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

export const AddPlayerModal: React.FC<Props> = ({
  addedUsers,
  addPlayerCallback,
  removePlayerCallback,
  query,
  setQuery,
}) => {
  // Find all users not already in the tournament

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

        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Add Users to Tournament </DialogTitle>
            <DialogDescription>
              Search for a user to add to the tournament. You can search by name
              or username.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4">
            <div className="grid gap-3">
              <Label htmlFor="name-1">Name</Label>
              <AddPlayerDropdown
                query={query}
                setQuery={setQuery}
                addPlayerCallback={addPlayerCallback}
                removePlayerCallback={removePlayerCallback}
                addedUsers={addedUsers}
                className=""
              />

              <div className="self-end p-5 pb-2 pt-2">
                <UserCreateModal query={query} setQuery={setQuery} />
              </div>
            </div>
          </div>
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
