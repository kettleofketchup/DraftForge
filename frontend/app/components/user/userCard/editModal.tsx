import React, { useEffect, useState, memo } from 'react';
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

import { Edit2, Plus, PlusCircle } from 'lucide-react';

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

import { UserEditForm } from '~/components/user/userCard/editForm';

interface Props {
  user: UserClassType;
}
export const UserEditModal: React.FC<Props> = memo(({ user }) => {
  const currentUser: UserType = useUserStore((state) => state.currentUser);

  const [form, setForm] = useState<UserType>({} as UserType);

  useEffect(() => {}, [user]);
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
                  size="icon"
                  variant="default"
                  className={
                    'bg-green-950 hover:bg-green-800 text-white' +
                    ' hover:shadow-sm hover:shadow-green-500/50'
                  }
                >
                  <Edit2 color="white" className="pzs-2" />
                </Button>
              </DialogTrigger>
            </TooltipTrigger>
            <TooltipContent>
              <p>Edit User </p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Edit User</DialogTitle>
            <DialogDescription>
              Please fill in the details below to edit the user.
            </DialogDescription>
          </DialogHeader>
          <UserEditForm user={user} form={form} setForm={setForm} />
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
          </DialogFooter>
        </DialogContent>
      </form>
    </Dialog>
  );
});

export default UserEditModal;
