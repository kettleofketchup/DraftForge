import React, { memo, useCallback, useEffect, useState } from 'react';
import type { UserClassType, UserType } from '~/components/user/types';

import { useOrgStore } from '~/store/orgStore';
import { useUserStore } from '~/store/userStore';

import { CancelButton, EditIconButton, SubmitButton } from '~/components/ui/buttons';
import {
  Dialog,
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

export const UserEditModal: React.FC<Props> = memo(({ user }) => {
  const currentUser: UserType = useUserStore((state) => state.currentUser);
  const setUser = useUserStore((state) => state.setUser);
  const currentOrg = useOrgStore((s) => s.currentOrg);

  const [open, setOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState<
    Partial<Record<keyof UserType, string>>
  >({});
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  // Initialize form with user data to prevent null updates
  const [form, setForm] = useState<UserType>(() => ({
    orgUserPk: user.orgUserPk,
    pk: user.pk,
    username: user.username,
    nickname: user.nickname,
    avatar: user.avatar,
    avatarUrl: user.avatarUrl,
    discordId: user.discordId,
    mmr: user.mmr,
    steam_account_id: user.steam_account_id,
    positions: user.positions,
    is_staff: user.is_staff,
    is_superuser: user.is_superuser,
    guildNickname: user.guildNickname,
  } as UserType));

  // Update form when user prop changes
  useEffect(() => {
    setForm({
      orgUserPk: user.orgUserPk,
      pk: user.pk,
      username: user.username,
      nickname: user.nickname,
      avatar: user.avatar,
      avatarUrl: user.avatarUrl,
      discordId: user.discordId,
      mmr: user.mmr,
      steam_account_id: user.steam_account_id,
      positions: user.positions,
      is_staff: user.is_staff,
      is_superuser: user.is_superuser,
      guildNickname: user.guildNickname,
    } as UserType);
  }, [user]);

  const onSubmit = useCallback(
    (e: React.MouseEvent | React.FormEvent) => {
      e.preventDefault();
      handleSave(e, {
        user,
        form,
        setForm,
        setErrorMessage,
        setIsSaving,
        setStatusMsg,
        setUser,
        organizationId: currentOrg?.pk ?? null,
        onSuccess: () => setOpen(false),
      });
    },
    [user, form, setUser, currentOrg?.pk],
  );

  if (!currentUser || (!currentUser.is_staff && !currentUser.is_superuser)) {
    return <></>;
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <EditIconButton tooltip="Edit User" data-testid="edit-user-btn" />
      </DialogTrigger>
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
            <SubmitButton
              loading={isSaving}
              loadingText="Saving..."
              onClick={onSubmit}
            >
              {user && user.pk ? 'Save Changes' : 'Create User'}
            </SubmitButton>
            <CancelButton onClick={() => setOpen(false)} />
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
});

export default UserEditModal;
