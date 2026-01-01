import type { FormEvent, JSX } from 'react';
import React from 'react';
import { toast } from 'sonner';
import type { UserClassType, UserType } from '~/components/user/types';
import { User } from '~/components/user/user';
import { getLogger } from '~/lib/logger';
const log = getLogger('handleSaveHook');

export const createErrorMessage = (
  val: Partial<Record<keyof UserType, string>>,
): JSX.Element => {
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

type HandleSaveParams = {
  user: UserClassType;
  form: UserType;
  setForm: React.Dispatch<React.SetStateAction<UserType>>;
  setErrorMessage: React.Dispatch<
    React.SetStateAction<Partial<Record<keyof UserType, string>>>
  >;
  setIsSaving: React.Dispatch<React.SetStateAction<boolean>>;
  setStatusMsg: React.Dispatch<React.SetStateAction<string | null>>;
  setUser: (user: UserType) => void;
  setDiscordUser?: React.Dispatch<React.SetStateAction<User>>;
};

export const handleSave = async (
  e: FormEvent,
  {
    user,
    form,
    setForm,
    setErrorMessage,
    setIsSaving,
    setStatusMsg,
    setUser,
    setDiscordUser,
  }: HandleSaveParams,
) => {
  setErrorMessage({}); // Clear old errors
  const newUser: User = new User(form as UserType); // Create a new User instance
  const resetForm = () => {
    log.debug('resetting form');
    if (setDiscordUser) {
      // Reset Discord user if setDiscordUser is provided
      log.debug('postSave: resetting Discord user');
      setDiscordUser(new User({} as UserClassType));
    }
    setForm({} as UserClassType); // Reset form after submission
    setIsSaving(false);
  };
  if (!user.pk) {
    toast.promise(newUser.dbCreate(), {
      loading: `Creating User ${user.username}.`,
      success: (data: UserType) => {
        setIsSaving(true);
        setStatusMsg('User created successfully!');
        setUser(data);
        resetForm();
        return `${user.username} has been Created`;
      },
      error: (err) => {
        const val = err.response.data;
        setErrorMessage(val);
        log.error('Failed to create user', err);
        return <>{createErrorMessage(val)}</>;
      },
    });
  } else {
    toast.promise(newUser.dbUpdate(form as UserType), {
      loading: `Updating User ${user.username}.`,
      success: (data) => {
        setIsSaving(true);
        setStatusMsg('User updated successfully!');
        setUser(data);
        resetForm();
        return `${user.username} has been updated`;
      },
      error: (err) => {
        log.error(`Failed to update user ${user.username}`, err);
        setErrorMessage(err.response.data);
        return `Failed to update user ${user.username}.`;
      },
    });
  }
};
