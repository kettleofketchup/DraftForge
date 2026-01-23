import { motion } from 'framer-motion';
import React, { memo, useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { Badge } from '~/components/ui/badge';
import type { UserClassType, UserType } from '~/components/user/types';
import { User } from '~/components/user/user';
import { AvatarUrl } from '~/index';
import { getLogger } from '~/lib/logger';
import { PlayerRemoveButton } from '~/pages/tournament/tabs/players/playerRemoveButton';
import { useUserStore } from '~/store/userStore';
import { RolePositions } from './positions';
import { UserRemoveButton } from './userCard/deleteButton';
import UserEditModal from './userCard/editModal';
const log = getLogger('UserCard');

interface Props {
  user: UserClassType;
  edit?: boolean;
  saveFunc?: string;
  compact?: boolean;
  deleteButtonType?: 'tournament' | 'normal';
  /** Animation delay index for staggered loading */
  animationIndex?: number;
}

export const UserCard: React.FC<Props> = memo(
  ({ user, edit, saveFunc, compact, deleteButtonType, animationIndex = 0 }) => {
    const [editMode, setEditMode] = useState(edit || false);
    const form = useForm<UserType>();

    const currentUser: UserType = useUserStore((state) => state.currentUser); // Zustand setter
    const [isSaving, setIsSaving] = useState(false);
    const [error, setError] = useState(false);
    const [errorMessage, setErrorMessage] = useState<
      Partial<Record<keyof UserType, string>>
    >({});
    const getUsers = useUserStore((state) => state.getUsers);

    const delUser = useUserStore((state) => state.delUser); // Zustand setter

    const [saveCallback, setSaveCallBack] = useState(saveFunc || 'save');
    useEffect(() => {
      if (!user.pk) {
        log.error('User does not have a primary key (pk)');
        getUsers();
      }
    }, [user, user.mmr, user.pk, user.username, user.nickname, user.position]);

    const hasError = () => {
      if (!user.mmr) {
        return true;
      }

      return false;
    };
    const avatar = () => {
      return (
        <>
          {user.avatar && (
            <div className="flex-row w-20 h-20">
              {!hasError() && (
                <img
                  src={AvatarUrl(user)}
                  alt={`${user.username}'s avatar`}
                  className="w-16 h-16 rounded-full border border-primary"
                />
              )}

              {hasError() && (
                <>
                  <span className="relative flex size-3 place-self-end mr-5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-sky-400 opacity-75" />
                    <span className="relative inline-flex size-3 rounded-full bg-red-500" />
                  </span>
                  <img
                    src={AvatarUrl(user)}
                    alt={`${user.username}'s avatar`}
                    className="flex w-16 h-16 rounded-full border border-primary"
                  />
                </>
              )}
            </div>
          )}
        </>
      );
    };

    const userHeader = () => {
      return (
        <>
          {!editMode && (
            <div className="flex-1">
              <h2 className="card-title text-lg">
                {user.nickname || user.username}
              </h2>
              {!compact && (
                <div className="flex gap-2 mt-1">
                  {user.is_staff && (
                    <Badge className="bg-blue-700 text-white">Staff</Badge>
                  )}
                  {user.is_superuser && (
                    <Badge className="bg-red-700 text-white">Admin</Badge>
                  )}
                </div>
              )}
            </div>
          )}
        </>
      );
    };

    const viewMode = () => {
      if (compact) {
        return (
          <>
            {user.mmr && (
              <div>
                <span className="font-semibold">MMR:</span> {user.mmr}
              </div>
            )}
            {user.username && (
              <div>
                <span className="font-semibold">Username:</span> {user.username}
              </div>
            )}
            {user.nickname && (
              <div>
                <span className="font-semibold">Nickname:</span> {user.nickname}
              </div>
            )}
            <RolePositions user={user} />
          </>
        );
      }
      return (
        <>
          {user.username && (
            <div>
              <span className="font-semibold">Username:</span> {user.username}
            </div>
          )}
          {user.nickname && (
            <div>
              <span className="font-semibold">Nickname:</span> {user.nickname}
            </div>
          )}

          {user.mmr && (
            <div>
              <span className="font-semibold">MMR:</span> {user.mmr}
            </div>
          )}

          <RolePositions user={user} />
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
          <a
            className="self-center btn btn-sm btn-outline"
            href={goToDotabuff()}
          >
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
      if (user.username) {
        result += user.username;
      }
      if (user.pk) {
        result += user.pk.toString();
      }
      return result;
    };

    const errorInfo = () => {
      return (
        <div className="flex flex-col items-end">
          {!user.mmr && (
            <span className="font-semibold text-red-500">MMR: Not added</span>
          )}
          {!user.positions && (
            <span className="font-semibold text-red-500">
              Position: Not added
            </span>
          )}
        </div>
      );
    };
    const topBar = () => {
      if (compact) {
        return (
          <>
            <div className="flex items-center gap-2 justify-center">
              {userHeader()}
              <div className="flex justify-end">
                {(currentUser.is_staff || currentUser.is_superuser) && (
                  <UserEditModal user={new User(user)} />
                )}
              </div>
            </div>
            <div className="flex items-center gap-2 py-4 justify-center">
              {avatar()}
            </div>
          </>
        );
      } else
        return (
          <div className="flex items-center gap-2 justify-start">
            {avatar()}
            {userHeader()}
            {(currentUser.is_staff || currentUser.is_superuser) && (
              <UserEditModal user={new User(user)} />
            )}
          </div>
        );
    };
    return (
      <div
        key={`usercard:${getKeyName()} base`}
        data-testid={`usercard-${user.username}`}
        className="flex w-full
        sm:gap-2 md:gap-4
        py-4
        justify-center
        content-center
        [content-visibility: auto] [contain-intrinsic-size: 400px 220px]"
      >
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.15, delay: Math.min(animationIndex * 0.02, 0.2) }}
          whileHover={{ scale: 1.02 }}
          key={`usercard:${getKeyName()} basediv`}
          className="justify-between p-2 h-full card bg-base-200 shadow-md w-full
            max-w-sm hover:bg-violet-900 . focus:outline-2
            hover:shadow-xl/30
            focus:outline-offset-2 focus:outline-violet-500
            focus:outline-offset-2 active:bg-violet-900"
        >
          {topBar()}

          <div className="mt-2 space-y-2 text-sm">
            {viewMode()}
            <div className="flex flex-col ">
              <div className="flex items-center justify-start gap-6">
                {userDotabuff()}
              </div>
              <div className="flex items-center justify-end gap-6">
                {errorInfo()}
                {currentUser.is_staff &&
                  saveCallback === 'save' &&
                  deleteButtonType === 'normal' && (
                    <UserRemoveButton user={user} />
                  )}
                {currentUser.is_staff &&
                  saveCallback === 'save' &&
                  deleteButtonType === 'tournament' && (
                    <PlayerRemoveButton user={user} />
                  )}
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    );
  },
);
