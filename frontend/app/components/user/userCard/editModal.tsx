import React, { memo, useEffect, useState } from 'react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip'; // Adjust path as needed
import type { UserClassType, UserType } from '~/components/user/types';

import { useUserStore } from '~/store/userStore';

import { Edit2 } from 'lucide-react';

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

import { DIALOG_CSS_SMALL } from '~/components/reusable/modal';
import { UserEditForm } from '~/components/user/userCard/editForm';
import { handleSave } from './handleSaveHook';

interface Props {
  user: UserClassType;
}
interface DialogProps {
  user: UserClassType;
  form: UserType;
  setForm: React.Dispatch<React.SetStateAction<UserType>>;
}
export const UserEditModalDialog: React.FC<DialogProps> = memo(
  ({ user, form, setForm }) => {
    const [errorMessage, setErrorMessage] = useState<
      Partial<Record<keyof UserType, string>>
    >({});
    const [isSaving, setIsSaving] = useState(false);
    const [statusMsg, setStatusMsg] = useState<string | null>(null);
    const setUser = useUserStore((state) => state.setUser);

    const onSubmit = (e: React.FormEvent) => {
      e.preventDefault();
      handleSave(e, {
        user: {} as UserClassType,

        form,
        setForm,
        setErrorMessage,
        setIsSaving,
        setStatusMsg,
        setUser,
      });
      setForm({} as UserType); // Reset form after
    };
    return (
      <DialogContent className={`${DIALOG_CSS_SMALL}`}>
        <DialogHeader>
          <DialogTitle>Edit User:</DialogTitle>
          <DialogDescription>
            Please fill in the details below to edit the user.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={onSubmit}>
          <UserEditForm user={user} form={form} setForm={setForm} />
        </form>
        <DialogFooter>
          <div className="flex flex-row justify-center align-center items-center w-full gap-4">
            <DialogClose asChild>
              <Button
                type="submit"
                className="bg-green-950 hover:bg-green-800 text-white hover:shadow-sm hover:shadow-green-500/50"
                disabled={isSaving}
                onClick={(e) => {
                  e.preventDefault();
                  handleSave(e, {
                    user: user,
                    form,
                    setForm,
                    setErrorMessage,
                    setIsSaving,
                    setStatusMsg,
                    setUser,
                  });
                }}
              >
                {user && user.pk
                  ? isSaving
                    ? 'Saving...'
                    : 'Save Changes'
                  : isSaving
                    ? 'Saving...'
                    : 'Create User'}
              </Button>
            </DialogClose>
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
          </div>
        </DialogFooter>
      </DialogContent>
    );
  },
);

export const UserEditModalButton: React.FC = memo(() => {
  return (
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
  );
});
export const UserEditModal: React.FC<Props> = memo(({ user }) => {
  const currentUser: UserType = useUserStore((state) => state.currentUser);

  const [form, setForm] = useState<UserType>({} as UserType);

  useEffect(() => {}, [user]);
  if (!currentUser || (!currentUser.is_staff && !currentUser.is_superuser)) {
    return <></>;
  }

  return (
    <Dialog key={`user-edit-modal-${user.id}`}>
      <form>
        <UserEditModalButton />
        <UserEditModalDialog user={user} form={form} setForm={setForm} />
      </form>
    </Dialog>
  );
});

export default UserEditModal;
