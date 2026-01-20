import type { FormEvent } from 'react';
import React, { useState } from 'react';
import type { UserClassType, UserType } from '~/components/user/types';

import { useUserStore } from '~/store/userStore';

import { toast } from 'sonner';
import { DialogClose } from '~/components/ui/dialog';
import { getLogger } from '~/lib/logger';

const log = getLogger('editForm');
interface Props {
  user: UserClassType; // Accepts both UserClassType and UserType
  form: UserType;
  setForm: React.Dispatch<React.SetStateAction<UserType>>;
}

export const TeamEditForm: React.FC<Props> = ({ user, form, setForm }) => {
  const currentUser: UserType = useUserStore((state) => state.currentUser); // Zustand setter
  const [errorMessage, setErrorMessage] = useState<
    Partial<Record<keyof UserType, string>>
  >({});

  const [isSaving, setIsSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>('null');
  const updateUserStore = useUserStore((state) => state.setUser); // Zustand setter
  const addUser = useUserStore((state) => state.addUser); // Zustand setter

  const handleChange = (field: keyof UserClassType, value: any) => {
    setForm((prev) => ({ ...prev, [field]: value }) as UserClassType);
  };

  if (!currentUser.is_staff && !currentUser.is_superuser) {
    return (
      <div className="text-error">
        You do not have permission to edit users.
      </div>
    );
  }
  const createErrorMessage = (val: Partial<Record<keyof UserType, string>>) => {
    if (!val || Object.keys(val).length === 0)
      return <h5>Error creating user:</h5>;

    return (
      <div className="text-error">
        <ul>
          {Object.entries(val).map(([field, message]) => (
            <li key={field}>{message}</li>
          ))}
        </ul>
      </div>
    );
  };

  const handleSave = async (e: FormEvent) => {
    setErrorMessage({}); // Clear old errors
    if (!user.pk) {
      toast.promise(user.dbCreate(), {
        loading: `Creating User ${user.username}.`,
        success: () => {
          setIsSaving(true);
          setStatusMsg('User created successfully!');
          addUser(user as UserType);
          return `${user.username} has been Created`;
        },
        error: (err) => {
          const val = err.response.data;
          setErrorMessage(val);
          log.error('Failed to create user', err);
          return <>{createErrorMessage(val)}</>;
        },
      });
      setIsSaving(false);
    } else {
      toast.promise(user.dbUpdate(form as UserType), {
        loading: `Updating User ${user.username}.`,
        success: (data) => {
          setIsSaving(true);
          setStatusMsg('User updated successfully!');
          updateUserStore(user as UserType); // Update Zustand store with the current instance
          return `${user.username} has been updated`;
        },
        error: (err) => {
          log.error(`Failed to update user ${user.username}`, err);
          setErrorMessage(err.response.data);
          return `Failed to update user ${user.username}.`;
        },
      });
      setIsSaving(false);
    }
  };

  const inputView = (key: keyof UserClassType, label: string, type: string = 'text') => {
    return (
      <div>
        <label className="font-semibold">{label}</label>
        <input
          type={type}
          placeholder={String(user[key] ?? '')}
          value={String(form[key as keyof UserType] ?? '')}
          onFocus={() => handleChange(key, user[key])}
          onChange={(e) =>
            handleChange(key, e.target.value)
          }
          className={`input input-bordered w-full mt-1 ${errorMessage[key as keyof UserType] ? 'input-error' : ''}`}
        />
        {errorMessage[key as keyof UserType] && (
          <p className="text-error text-sm mt-1">{errorMessage[key as keyof UserType]}</p>
        )}
      </div>
    );
  };
  return (
    <>
      {/* {inputView('username', 'Username: ')} */}
      {inputView('nickname', 'Nickname: ')}
      {inputView('mmr', 'MMR: ', 'number')}
      {inputView('position', 'Position: ')}
      {inputView('steamid', 'Steam ID: ', 'number')}
      {/* {inputView('discordId', 'Discord ID: ', 'number')} */}
      {inputView('guildNickname', 'Discord Guild Nickname: ')}
      <div className="flex flex-row items-start gap-4">
        <DialogClose asChild>
          <button
            onClick={handleSave}
            className="btn btn-primary btn-sm mt-3"
            disabled={isSaving}
          >
            {user && user.pk && (isSaving ? 'Saving...' : 'Save Changes')}
            {user && !user.pk && (isSaving ? 'Saving...' : 'Create User')}
          </button>
        </DialogClose>
      </div>
    </>
  );
};
