import React, { use, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type {
  GuildMember,
  UserType,
  UserClassType,
} from '~/components/user/types';

import { useUserStore } from '~/store/userStore';

import { Button } from '~/components/ui/button';
import { Label } from '~/components/ui/label';
import { Input } from '~/components/ui/input';
import { User } from '~/components/user/user';

import { DialogClose } from '~/components/ui/dialog';
import { Toaster } from '~/components/ui/sonner';

interface Props {
  user: UserClassType; // Accepts both UserClassType and UserType
  form: UserType;
  setForm: React.Dispatch<React.SetStateAction<UserType>>;
}
import { toast } from 'sonner';
import { UserRoundPlusIcon } from 'lucide-react';
import { getTournaments } from '~/components/api/api';
export const UserToast = (title: string) => {
  const toastTitle = () => {
    return (
      <div>
        <UserRoundPlusIcon className="mr-2 h-4 w-4 inline-block" />
        <span className="font-semibold">{title}</span>
      </div>
    );
  };
  toast(toastTitle(), {
    description: 'Sunday, December 03, 2023 at 9:00 AM',
  });
};
export const UserEditForm: React.FC<Props> = ({ user, form, setForm }) => {
  const currentUser: UserType = useUserStore((state) => state.currentUser); // Zustand setter
  const [errorMessage, setErrorMessage] = useState<
    Partial<Record<keyof UserType, string>>
  >({});

  const [isSaving, setIsSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>('null');
  const updateUserStore = useUserStore((state) => state.setUser); // Zustand setter
  const addUser = useUserStore((state) => state.addUser); // Zustand setter
  const getUsers = useUserStore((state) => state.getUsers); // Zustand setter
  const setUser = useUserStore((state) => state.setUser); // Zustand setter
  const handleChange = (field: keyof UserClassType, value: any) => {
    setForm((prev) => ({ ...prev, [field]: value }) as UserClassType);
  };
  useEffect(() => {
    setForm(user as UserType); // Initialize form with user data

    if (user.username !== form.username) {
      setForm({} as UserType); // Reset form if username changes
      setForm(user as UserType); // Ensure form is set to the user data
    }
  }, [user]);
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
    const newUser: User = new User(user as UserType); // Create a new User instance
    if (!user.pk) {
      toast.promise(newUser.dbCreate(), {
        loading: `Creating User ${user.username}.`,
        success: (data: UserType) => {
          setIsSaving(true);
          setStatusMsg('User created successfully!');
          setUser(data);
          return `${user.username} has been Created`;
        },
        error: (err) => {
          const val = err.response.data;
          setErrorMessage(val);
          console.error('Failed to create user', err);
          return <>{createErrorMessage(val)}</>;
        },
      });

      setIsSaving(false);
    } else {
      toast.promise(newUser.dbUpdate(form as UserType), {
        loading: `Updating User ${user.username}.`,
        success: (data) => {
          setIsSaving(true);
          setStatusMsg('User updated successfully!');
          setUser(data);

          return `${user.username} has been updated`;
        },
        error: (err) => {
          console.error(`Failed to update user ${user.username}`, err);
          setErrorMessage(err.response.data);
          return `Failed to update user ${user.username}.`;
        },
      });
      setIsSaving(false);
    }
  };

  const inputView = (key: string, label: string, type: string = 'text') => {
    return (
      <div>
        <label className="font-semibold">{label}</label>
        <input
          type={type}
          placeholder={user[key] ?? ''}
          value={form[key] ?? ''}
          onFocus={() => handleChange(key as keyof UserClassType, user[key])}
          onChange={(e) =>
            handleChange(key as keyof UserClassType, e.target.value)
          }
          className={`input input-bordered w-full mt-1 ${errorMessage[key] ? 'input-error' : ''}`}
        />
        {errorMessage[key] && (
          <p className="text-error text-sm mt-1">{errorMessage[key]}</p>
        )}
      </div>
    );
  };
  return (
    <>
      <div>
        <label className="font-semibold">Username: {user.username}</label>
      </div>
      {inputView('nickname', 'Nickname: ')}
      {inputView('mmr', 'MMR: ', 'number')}
      {inputView('position', 'Position: ')}
      {inputView('steam_id', 'Steam ID: ', 'number')}
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
