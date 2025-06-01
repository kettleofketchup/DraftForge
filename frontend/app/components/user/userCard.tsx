import React, { use, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type { UserClassType, UserType } from './types';
import axios from '../api/axios';
import { deleteUser } from '../api/api';
import { useNavigate } from 'react-router';
import { useUserStore } from '~/store/userStore';
import { User } from './user';
import { DeleteButton } from '~/components/reusable/deleteButton';
interface Props {
  user: User;
  edit?: boolean;
  saveFunc?: string;
  compact?: boolean;
}

export const UserCard: React.FC<Props> = ({
  user,
  edit,
  saveFunc,
  compact,
}) => {
  const [editMode, setEditMode] = useState(edit || false);
  const [form, setForm] = useState<User>(user ?? new User({} as UserType));
  const currentUser: UserType = useUserStore((state) => state.currentUser); // Zustand setter
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(false);
  const [errorMessage, setErrorMessage] = useState<
    Partial<Record<keyof UserType, string>>
  >({});
  const getUsers = useUserStore((state) => state.getUsers);

  const addUser = useUserStore((state) => state.addUser); // Zustand setter
  const delUser = useUserStore((state) => state.delUser); // Zustand setter

  const handleChange = (field: keyof UserClassType, value: any) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSave = async (e: FormEvent) => {
    e.stopPropagation();
    setErrorMessage({}); // clear old errors

    if (saveFunc === 'create') {
      setIsSaving(true);
      try {
        await axios.post(`/register`, form);
        addUser(form);
        setForm({ username: 'Success!' } as UserType);
        // Close the modal
        const modalCheckbox = document.getElementById(
          'create_user_modal',
        ) as HTMLInputElement;
        if (modalCheckbox) modalCheckbox.checked = false;
      } catch (err) {
        console.error('Failed to create user', err);
        setErrorMessage(err.response.data);
        setError(true);
      } finally {
        setIsSaving(false);
      }
    } else if (saveFunc === 'save') {
      if (!form.pk) return;
      setIsSaving(true);
      try {
        await axios.patch(`/users/${user.pk}/`, form);
        setEditMode(false);
        setError(false);
        getUsers(); // Triggers fetch and repopulates store
      } catch (err) {
        setError(true);
        setErrorMessage(err.response.data);

        console.error('Failed to update user', err);
      } finally {
        setIsSaving(false);
      }
    }
  };
  const handleDelete = async (e: FormEvent) => {
    e.stopPropagation();
    setErrorMessage({}); // clear old errors
    setIsSaving(true);
    try {
      await deleteUser(user?.pk);
      console.log('User deleted successfully');
      setError(false);
      setForm({ username: 'Success!' } as UserType);
      delUser(form);
      // Close the modal
      const modalCheckbox = document.getElementById(
        'create_user_modal',
      ) as HTMLInputElement;
      if (modalCheckbox) modalCheckbox.checked = false;
    } catch (err) {
      console.error('Failed to delete user', err);
      setErrorMessage(err.response.data);

      setError(true);
    } finally {
      setIsSaving(false);
    }
  };
  const [saveCallback, setSaveCallBack] = useState(saveFunc || 'save');

  useEffect(() => {}, [user, isSaving]);

  useEffect(() => {
    console.log('reset form', user);
    setForm(user);
  }, [user]);

  const avatar = () => {
    return (
      <>
        {user.avatar && (
          <img
            src={user.avatarUrl}
            alt={`${user.username}'s avatar`}
            className="w-16 h-16 rounded-full border border-primary"
          />
        )}
      </>
    );
  };

  const userHeader = () => {
    return (
      <>
        {!editMode && (
          <div className="flex-1">
            <h2 className="card-title text-lg">{user.username}</h2>
            {!compact && (
              <div className="flex gap-2 mt-1">
                {user.is_staff && (
                  <span className="badge badge-warning">Staff</span>
                )}
                {user.is_superuser && (
                  <span className="badge badge-error">Admin</span>
                )}
              </div>
            )}
          </div>
        )}
      </>
    );
  };

  const editModeView = () => {
    const inputView = (key: string, label: string, type: string = 'text') => {
      return (
        <div>
          <label className="font-semibold">{label}</label>
          <input
            type={type}
            value={form[key] ?? ''}
            onChange={(e) => handleChange(key, e.target.value)}
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
        {inputView('username', 'Username: ')}
        {inputView('nickname', 'Nickname: ')}
        {inputView('mmr', 'MMR: ', 'number')}
        {inputView('position', 'Position: ')}
        {inputView('steam_id', 'Steam ID: ', 'number')}
        {inputView('discordId', 'Discord ID: ', 'number')}
        {inputView('guildNickname', 'Discord Guild Nickname: ')}
        <div className="flex flex-row items-start gap-4">
          {saveCallback === 'save' && (
            <DeleteButton
              onClick={handleDelete}
              tooltipText="Delete the user"
              className="btn-sm mt-3"
              disabled={isSaving}
            />
          )}
          <button
            onClick={handleSave}
            className="btn btn-primary btn-sm mt-3"
            disabled={isSaving}
          >
            {saveCallback === 'create' &&
              (isSaving ? 'Saving...' : 'Create User')}
            {saveCallback === 'save' &&
              (isSaving ? 'Saving...' : 'Save Changes')}
          </button>
        </div>
      </>
    );
  };

  const viewMode = () => {
    if (compact) {
      return (
        <>
          {user.mmr !== undefined && (
            <div>
              <span className="font-semibold">MMR:</span> {user.mmr}
            </div>
          )}

          {user.position && (
            <div>
              <span className="font-semibold">Position:</span> {user.position}
            </div>
          )}
        </>
      );
    }
    return (
      <>
        {user.nickname !== undefined && (
          <div>
            <span className="font-semibold">Nickname:</span> {user.nickname}
          </div>
        )}

        {user.mmr !== undefined && (
          <div>
            <span className="font-semibold">MMR:</span> {user.mmr}
          </div>
        )}

        {user.position && (
          <div>
            <span className="font-semibold">Position:</span> {user.position}
          </div>
        )}
        {user.steamid && (
          <div>
            <span className="font-semibold">Steam ID:</span> {user.steamid}
          </div>
        )}
      </>
    );
  };

  const userDotabuff = () => {
    const goToDotabuff = () => {
      return `https://www.dotabuff.com/players/${user.steamid}`;
    };
    if (!user.steamid) return <></>;
    return (
      <>
        <a className="btn btn-sm btn-outline ml-auto" href={goToDotabuff()}>
          <span className="flex items-center">
            <img
              src="https://cdn.brandfetch.io/idKrze_WBi/w/96/h/96/theme/dark/logo.png?c=1dxbfHSJFAPEGdCLU4o5B"
              alt="Dotabuff Logo"
              className="w-4 h-4 mr-2"
            />
            Dotabuff Profile
          </span>
        </a>
      </>
    );
  };
  const getKeyName = () => {
    let result = '';
    if (user.pk) {
      result += user.pk.toString();
    }
    if (user.username) {
      result += user.username;
    }
    return result;
  };
  return (
    <div
      key={`usercard:${getKeyName()} base`}
      className="px-6 py-4 gap-6 content-center"
    >
      <div
        className=" p-2 h-full card bg-base-200 shadow-md w-full
            max-w-sm hover:bg-violet-900 . focus:outline-2
            hover:shadow-xl/30
            focus:outline-offset-2 focus:outline-violet-500
            focus:outline-offset-2 active:bg-violet-900
            delay-700 duration-900 ease-in-out"
      >
        <div className="flex items-center gap-2">
          {avatar()}
          {userHeader()}
          {(currentUser.is_staff || currentUser.is_superuser) && (
            <>
              {saveCallback !== 'create' && (
                <button
                  className="btn btn-sm btn-outline ml-auto"
                  onClick={() => setEditMode(!editMode)}
                >
                  {editMode ? 'Cancel' : 'Edit'}
                </button>
              )}
            </>
          )}
        </div>
        <div className="mt-4 space-y-2 text-sm">
          {editMode ? editModeView() : viewMode()}
        </div>
        {userDotabuff()}
      </div>
    </div>
  );
};
