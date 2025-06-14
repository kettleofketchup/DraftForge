import React, { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type {
  GuildMember,
  UserType,
  UserClassType,
} from '~/components/user/types';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip'; // Adjust path as needed
import { UserCard } from '~/components/user/userCard';
import axios from '~/components/api/axios';
import { useUserStore } from '~/store/userStore';
import {
  Combobox,
  ComboboxInput,
  ComboboxOption,
  ComboboxOptions,
} from '@headlessui/react';
import Footer from '~/components/footer';
import DiscordUserDropdown from '~/components/user/DiscordUserDropdown';
import { User } from '~/components/user/user';
interface Props {
  users: UserType[];
  query: string;
  setQuery: React.Dispatch<React.SetStateAction<string>>;
}

import { Tab, TabGroup, TabList, TabPanel, TabPanels } from '@headlessui/react';
import type { GameType, TournamentType } from '~/components/tournament/types'; // Adjust the import path as necessary
import { Plus, PlusCircle } from 'lucide-react';

import { UsersDropdown } from '~/components/user/UsersDropdown';
import { SearchUserDropdown } from '~/components/user/searchUser';
import { useNavigate } from 'react-router-dom';
import { updateTournament } from '~/components/api/api';
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
import { Button } from '~/components/ui/button';
import { Label } from '~/components/ui/label';
import { Input } from '~/components/ui/input';
import { LucidePlus } from 'lucide-react';
import { AddPlayerDropdown } from './addPlayerDropdown';
import UserCreateModal from '~/components/user/userCard/createModal';
import Tournament from '~/pages/tournaments/tournaments';
interface Props {
  users: UserType[];

  addedUsers?: UserType[];
  query: string;
  setQuery: React.Dispatch<React.SetStateAction<string>>;
  addPlayerCallback?: (user: UserType) => Promise<void>;
  removePlayerCallback?: (e: FormEvent, user: UserType) => Promise<void>;
}

export const AddPlayerModal: React.FC<Props> = ({
  users,
  addedUsers,
  addPlayerCallback,
  removePlayerCallback,
  query,
  setQuery,
}) => {
  const allUsers = useUserStore((state) => state.users); // Zustand setter

  const user: UserType = useUserStore((state) => state.currentUser); // Zustand setter
  const getUsers = useUserStore((state) => state.getUsers); // Zustand setter

  const [selectedDiscordUser, setSelectedDiscordUser] = useState(
    new User({} as UserClassType),
  );
  const [searchedPerson, setSearchedPerson] = useState(
    new User({} as UserClassType),
  );

  let navigate = useNavigate();
  useEffect(() => {
    if (!allUsers || allUsers.length === 0) {
      useUserStore.getState().getUsers();
    }
  }, [users]);
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
                users={allUsers}
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
