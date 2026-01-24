import { motion } from 'framer-motion';
import React, { memo, useEffect } from 'react';
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
  saveFunc?: string;
  compact?: boolean;
  deleteButtonType?: 'tournament' | 'normal';
  /** Animation delay index for staggered loading */
  animationIndex?: number;
}

export const UserCard: React.FC<Props> = memo(
  ({ user, saveFunc = 'save', compact, deleteButtonType, animationIndex = 0 }) => {
    const currentUser: UserType = useUserStore((state) => state.currentUser);
    const getUsers = useUserStore((state) => state.getUsers);

    useEffect(() => {
      if (!user.pk) {
        log.error('User does not have a primary key (pk)');
        getUsers();
      }
    }, [user.pk, getUsers]);

    const hasError = () => {
      if (!user.mmr) {
        return true;
      }

      return false;
    };
    const avatar = () => {
      if (!user.avatar) return null;
      return (
        <div className="relative">
          {hasError() && (
            <span className="absolute -top-1 -right-1 flex size-3 z-10">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-sky-400 opacity-75" />
              <span className="relative inline-flex size-3 rounded-full bg-red-500" />
            </span>
          )}
          <img
            src={AvatarUrl(user)}
            alt={`${user.username}'s avatar`}
            className="w-14 h-14 rounded-full border-2 border-primary"
          />
        </div>
      );
    };


    const userDetails = () => {
      return (
        <div className="text-xs text-text-muted space-y-0.5">
          {user.username && (
            <div className="truncate">
              <span className="font-semibold">Username:</span> {user.username}
            </div>
          )}
          {user.nickname && user.nickname !== user.username && (
            <div className="truncate">
              <span className="font-semibold">Nickname:</span> {user.nickname}
            </div>
          )}
          {user.mmr && (
            <div>
              <span className="font-semibold">MMR:</span> {user.mmr}
            </div>
          )}
        </div>
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
    const showDeleteButton = currentUser.is_staff && saveFunc === 'save' && deleteButtonType;

    return (
      <div
        key={`usercard:${getKeyName()} base`}
        data-testid={`usercard-${user.username}`}
        className="flex w-full py-2 justify-center content-center
          [content-visibility:auto] [contain-intrinsic-size:400px_160px]"
      >
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.15, delay: Math.min(animationIndex * 0.02, 0.2) }}
          whileHover={{ scale: 1.02 }}
          key={`usercard:${getKeyName()} basediv`}
          className="relative flex flex-col p-3 pb-12 card bg-base-300 shadow-elevated w-full
            max-w-sm hover:bg-base-200 focus:outline-2
            focus:outline-offset-2 focus:outline-primary
            active:bg-base-200 transition-all duration-300 ease-in-out"
        >
          {/* Header row - name and edit button */}
          <div className="flex items-center justify-between mb-2">
            <div className="flex-1 min-w-0">
              <h2 className="card-title text-base truncate">
                {user.nickname || user.username}
              </h2>
              {!compact && (user.is_staff || user.is_superuser) && (
                <div className="flex gap-1 mt-0.5">
                  {user.is_staff && (
                    <Badge className="bg-blue-700 text-white text-[10px] px-1.5 py-0">Staff</Badge>
                  )}
                  {user.is_superuser && (
                    <Badge className="bg-red-700 text-white text-[10px] px-1.5 py-0">Admin</Badge>
                  )}
                </div>
              )}
            </div>
            {(currentUser.is_staff || currentUser.is_superuser) && (
              <UserEditModal user={new User(user)} />
            )}
          </div>

          {/* 2-column layout: Avatar left, Positions right */}
          <div className="grid grid-cols-[auto_1fr] gap-3 items-center">
            {/* Left column - Avatar centered */}
            <div className="flex items-center justify-center">
              {avatar()}
            </div>

            {/* Right column - Positions (compact mode) */}
            <div className="flex flex-col gap-1">
              <RolePositions user={user} compact />
            </div>
          </div>

          {/* User details row - above footer */}
          <div className="mt-2 mb-1 flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              {userDetails()}
            </div>
            <div className="flex-shrink-0">
              {errorInfo()}
            </div>
          </div>

          {/* Card Footer - fixed to bottom */}
          <div className="absolute bottom-2 left-3 right-3 flex items-end justify-between">
            {/* Dotabuff - bottom left */}
            <div className="flex-shrink-0">
              {userDotabuff()}
            </div>

            {/* Delete button - bottom right */}
            {showDeleteButton && (
              <div className="flex-shrink-0">
                {deleteButtonType === 'normal' && (
                  <UserRemoveButton user={user} />
                )}
                {deleteButtonType === 'tournament' && (
                  <PlayerRemoveButton user={user} />
                )}
              </div>
            )}
          </div>
        </motion.div>
      </div>
    );
  },
);
