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

import { useUserStore } from '~/store/userStore';

import { Edit2, Plus, PlusCircle, PlusCircleIcon } from 'lucide-react';

import { useNavigate } from 'react-router-dom';
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
import { User } from '~/components/user/user';

import { UserEditForm } from '~/components/user/userCard/editForm';
import DiscordUserDropdown from '~/components/user/DiscordUserDropdown';

interface Props {}
export const TeamCreateModal: React.FC<Props> = (props) => {
  const currentUser: UserType = useUserStore((state) => state.currentUser); // Zustand setter
  const users: UserType[] = useUserStore((state) => state.users); // Zustand setter

  const [selectedDiscordUser, setSelectedDiscordUser] = useState<User>(
    new User({} as UserClassType),
  );
  const [form, setForm] = useState<UserType>({} as UserType);

  const handleDiscordUserSelect = (user: GuildMember) => {
    setForm({} as UserType);
    console.log(selectedDiscordUser);
    selectedDiscordUser.setFromGuildMember(user);
    //This is necessary because we need a new instance of user to trigger a re-render
    setSelectedDiscordUser(new User(selectedDiscordUser as UserType));
    setForm(selectedDiscordUser as UserType);
  };

  const [query, setQuery] = useState<string>('');
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
                  <PlusCircleIcon size="lg" color="white" className="p-2" />
                  Create Team
                </Button>
              </DialogTrigger>
            </TooltipTrigger>
            <TooltipContent>
              <p>Create Team </p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Create User</DialogTitle>
            <DialogDescription>
              Please fill in the details below to create a new teamzs.
            </DialogDescription>
          </DialogHeader>
          <DiscordUserDropdown
            query={query}
            setQuery={setQuery}
            discrimUsers={users}
            onSelect={handleDiscordUserSelect}
          />

          <UserEditForm
            user={selectedDiscordUser}
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

export default TeamCreateModal;
