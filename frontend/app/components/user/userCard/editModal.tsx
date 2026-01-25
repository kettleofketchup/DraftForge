import React, { memo, useEffect, useState } from 'react';
import type { UserClassType, UserType } from '~/components/user/types';

import { useUserStore } from '~/store/userStore';

import { Button } from '~/components/ui/button';
import { CancelButton, EditIconButton, SubmitButton } from '~/components/ui/buttons';
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
              <SubmitButton
                loading={isSaving}
                loadingText="Saving..."
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
                {user && user.pk ? 'Save Changes' : 'Create User'}
              </SubmitButton>
            </DialogClose>
            <DialogClose asChild>
              <CancelButton />
            </DialogClose>
          </div>
        </DialogFooter>
      </DialogContent>
    );
  },
);

export const UserEditModalButton: React.FC = memo(() => {
  return (
    <DialogTrigger asChild>
      <EditIconButton tooltip="Edit User" />
    </DialogTrigger>
  );
});
export const UserEditModal: React.FC<Props> = memo(({ user }) => {
  const currentUser: UserType = useUserStore((state) => state.currentUser);

  // Initialize form with user data to prevent null updates
  const [form, setForm] = useState<UserType>(() => ({
    pk: user.pk,
    username: user.username,
    nickname: user.nickname,
    avatar: user.avatar,
    avatarUrl: user.avatarUrl,
    discordId: user.discordId,
    mmr: user.mmr,
    steamid: user.steamid,
    positions: user.positions,
    is_staff: user.is_staff,
    is_superuser: user.is_superuser,
    guildNickname: user.guildNickname,
  } as UserType));

  // Update form when user prop changes
  useEffect(() => {
    setForm({
      pk: user.pk,
      username: user.username,
      nickname: user.nickname,
      avatar: user.avatar,
      avatarUrl: user.avatarUrl,
      discordId: user.discordId,
      mmr: user.mmr,
      steamid: user.steamid,
      positions: user.positions,
      is_staff: user.is_staff,
      is_superuser: user.is_superuser,
      guildNickname: user.guildNickname,
    } as UserType);
  }, [user]);

  if (!currentUser || (!currentUser.is_staff && !currentUser.is_superuser)) {
    return <></>;
  }

  return (
    <Dialog key={`user-edit-modal-${user.pk}`}>
      <form>
        <UserEditModalButton />
        <UserEditModalDialog user={user} form={form} setForm={setForm} />
      </form>
    </Dialog>
  );
});

export default UserEditModal;
