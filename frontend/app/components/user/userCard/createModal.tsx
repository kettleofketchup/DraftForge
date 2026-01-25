import React, { useEffect, useState } from 'react';
import type {
  GuildMember,
  UserClassType,
  UserType,
} from '~/components/user/types';

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';

import { useUserStore } from '~/store/userStore';

import { PlusCircleIcon } from 'lucide-react';

import { Button } from '~/components/ui/button';
import { CancelButton, SubmitButton } from '~/components/ui/buttons';
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
import { User } from '~/components/user/user';

import { useShallow } from 'zustand/react/shallow';
import { DIALOG_CSS_SMALL } from '~/components/reusable/modal';
import DiscordUserDropdown from '~/components/user/DiscordUserDropdown';
import { UserEditForm } from '~/components/user/userCard/editForm';
import { getLogger } from '~/lib/logger';
import { handleSave } from './handleSaveHook';
const log = getLogger('createModal');

interface Props {
  query?: string;
  setQuery?: React.Dispatch<React.SetStateAction<string>>;
}

export const UserCreateModal: React.FC<Props> = ({ query, setQuery }) => {
  const currentUser: UserType = useUserStore((state) => state.currentUser);
  const users: UserType[] = useUserStore(useShallow((state) => state.users));

  const [selectedDiscordUser, setSelectedDiscordUser] = useState<User>(
    new User({} as UserClassType),
  );
  const [form, setForm] = useState<UserType>({} as UserType);
  const [errorMessage, setErrorMessage] = useState<
    Partial<Record<keyof UserType, string>>
  >({});
  const [isSaving, setIsSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>('null');
  const setUser = useUserStore((state) => state.setUser);

  const handleDiscordUserSelect = (user: GuildMember) => {
    setForm({} as UserType);
    setSelectedDiscordUser(new User({} as UserClassType));
    selectedDiscordUser.setFromGuildMember(user);
    setSelectedDiscordUser(new User(selectedDiscordUser as UserClassType));
    setForm(selectedDiscordUser as UserType);
    log.debug('Selected Discord User:', selectedDiscordUser);
  };

  useEffect(() => {
    log.debug('Form updated:', form);
  }, [form, selectedDiscordUser]);

  if (!currentUser || (!currentUser.is_staff && !currentUser.is_superuser)) {
    return <></>;
  }

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSave(e, {
      user: selectedDiscordUser,
      form,
      setForm,
      setErrorMessage,
      setIsSaving,
      setStatusMsg,
      setUser,
    });
    setForm({} as UserType); // Reset form after submission
    setSelectedDiscordUser(new User({} as UserClassType));
  };

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
                    'bg-emerald-600 hover:bg-emerald-500 text-white' +
                    ' shadow-lg shadow-emerald-900/50 border-b-4 border-b-emerald-800' +
                    ' active:border-b-0 active:translate-y-1 transition-all duration-75' +
                    ' hover:shadow-emerald-500/50'
                  }
                >
                  <PlusCircleIcon className="text-white" />
                  Create User
                </Button>
              </DialogTrigger>
            </TooltipTrigger>
            <TooltipContent>
              <p>Create a new user from discord </p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <DialogContent className={`${DIALOG_CSS_SMALL}`}>
          <DialogHeader>
            <DialogTitle>Create User</DialogTitle>
            <DialogDescription>
              Please fill in the details below to create a new user.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={onSubmit}>
            <div className="w-full mb-2">
              <DiscordUserDropdown
                query={query}
                setQuery={setQuery}
                discrimUsers={users}
                onSelect={handleDiscordUserSelect}
              />
            </div>

            <UserEditForm
              user={selectedDiscordUser}
              form={form}
              setForm={setForm}
            />
          </form>

          <DialogFooter>
            <div className="flex flex-row  gap-x-4 sm:gap-x-8 justify-center align-center items-center w-full">
              <DialogClose asChild>
                <SubmitButton
                  loading={isSaving}
                  loadingText="Saving..."
                  onClick={(e) => {
                    e.preventDefault();
                    handleSave(e, {
                      user: selectedDiscordUser,
                      form,
                      setForm,
                      setErrorMessage,
                      setIsSaving,
                      setStatusMsg,
                      setUser,
                      setDiscordUser: setSelectedDiscordUser,
                    });
                  }}
                >
                  {selectedDiscordUser && selectedDiscordUser.pk
                    ? 'Save Changes'
                    : 'Create User'}
                </SubmitButton>
              </DialogClose>
              <DialogClose asChild>
                <CancelButton />
              </DialogClose>
            </div>
          </DialogFooter>
        </DialogContent>
      </form>
    </Dialog>
  );
};

export default UserCreateModal;
