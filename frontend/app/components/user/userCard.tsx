import { motion } from 'framer-motion';
import React, { memo, useEffect } from 'react';
import { Badge } from '~/components/ui/badge';
import { ViewIconButton } from '~/components/ui/buttons';
import {
  CardAction,
  CardDescription,
  CardHeader,
  CardTitle,
} from '~/components/ui/card';
import { Item, ItemContent, ItemTitle } from '~/components/ui/item';
import { useSharedPopover } from '~/components/ui/shared-popover-context';
import type { UserClassType, UserType } from '~/components/user/types';
import { User } from '~/components/user/user';
import { UserAvatar } from '~/components/user/UserAvatar';
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
  /** Optional league ID for context-specific stats in mini profile */
  leagueId?: number;
  /** Optional organization ID for context-specific stats in mini profile */
  organizationId?: number;
}

export const UserCard: React.FC<Props> = memo(
  ({ user, saveFunc = 'save', compact, deleteButtonType, animationIndex = 0, leagueId, organizationId }) => {
    const currentUser: UserType = useUserStore((state) => state.currentUser);
    const getUsers = useUserStore((state) => state.getUsers);
    const { openPlayerModal } = useSharedPopover();

    const handleViewProfile = () => {
      openPlayerModal(user, { leagueId, organizationId });
    };

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
      return (
        <div className="relative">
          {hasError() && (
            <span className="absolute -top-1 -right-1 flex size-3 z-10">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-sky-400 opacity-75" />
              <span className="relative inline-flex size-3 rounded-full bg-red-500" />
            </span>
          )}
          <UserAvatar user={user} size="xl" border="primary" />
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
          className="flex flex-col gap-2 card card-compact bg-base-300 rounded-2xl w-fit
            hover:bg-base-200 focus:outline-2
            focus:outline-offset-2 focus:outline-primary
            active:bg-base-200"
        >
          {/* Header: 2-col layout with name/badges left, actions right */}
          <CardHeader className="p-0 gap-0.5">
            <CardTitle className="text-base truncate">
              {user.nickname || user.username}
            </CardTitle>
            {!compact && (user.is_staff || user.is_superuser) && (
              <CardDescription className="flex gap-1">
                {user.is_staff && (
                  <Badge className="bg-blue-700 text-white text-[10px] px-1.5 py-0">Staff</Badge>
                )}
                {user.is_superuser && (
                  <Badge className="bg-red-700 text-white text-[10px] px-1.5 py-0">Admin</Badge>
                )}
              </CardDescription>
            )}
            <CardAction className="flex items-center gap-1">
              {(currentUser.is_staff || currentUser.is_superuser) && (
                <UserEditModal user={new User(user)} />
              )}
              <ViewIconButton
                onClick={handleViewProfile}
                tooltip="View Profile"
              />
            </CardAction>
          </CardHeader>

          {/* 2-column layout: Avatar left, Positions right */}
          <div className="grid grid-cols-[auto_1fr] gap-2 items-center">
            {/* Left column - Avatar centered */}
            <div className="flex items-center justify-center">
              {avatar()}
            </div>

            {/* Right column - Positions and MMR */}
            <div className="flex flex-col gap-1 w-full">
              <Item size="sm" variant="muted" className="!p-1.5 w-full">
                <ItemContent className="!gap-1 items-center w-full">
                  <ItemTitle className="!text-xs text-muted-foreground">Positions</ItemTitle>
                  <RolePositions user={user} compact />
                </ItemContent>
              </Item>
              {/* MMR row */}
              <div className="grid grid-cols-2 gap-1 w-full">
                <Item size="sm" variant="muted" className="!p-1">
                  <ItemContent className="!gap-0 items-center">
                    <ItemTitle className="!text-xs text-muted-foreground">Base MMR</ItemTitle>
                    <span className="text-sm font-semibold">{user.mmr ?? '?'}</span>
                  </ItemContent>
                </Item>
                <Item size="sm" variant="muted" className="!p-1">
                  <ItemContent className="!gap-0 items-center">
                    <ItemTitle className="!text-xs text-muted-foreground">League MMR</ItemTitle>
                    <span className="text-sm font-semibold">?</span>
                  </ItemContent>
                </Item>
              </div>
            </div>
          </div>

          {/* User info row - 2 items per row */}
          <div className="grid grid-cols-2 gap-1">
            {user.username && (
              <Item size="sm" variant="muted" className="!p-1">
                <ItemContent className="!gap-0">
                  <ItemTitle className="!text-xs text-muted-foreground">Username</ItemTitle>
                  <span className="text-sm">{user.username.length > 8 ? `${user.username.slice(0, 8)}...` : user.username}</span>
                </ItemContent>
              </Item>
            )}
            {user.nickname && user.nickname !== user.username && (
              <Item size="sm" variant="muted" className="!p-1">
                <ItemContent className="!gap-0">
                  <ItemTitle className="!text-xs text-muted-foreground">Nickname</ItemTitle>
                  <span className="text-sm">{user.nickname.length > 8 ? `${user.nickname.slice(0, 8)}...` : user.nickname}</span>
                </ItemContent>
              </Item>
            )}
            {user.steamid && (
              <Item size="sm" variant="muted" className="!p-1">
                <ItemContent className="!gap-0">
                  <ItemTitle className="!text-xs text-muted-foreground">Steam ID</ItemTitle>
                  <span className="text-sm">{String(user.steamid).length > 8 ? `${String(user.steamid).slice(0, 8)}...` : user.steamid}</span>
                </ItemContent>
              </Item>
            )}
          </div>

          {/* Error info row */}
          {(!user.mmr || !user.positions) && (
            <div className="flex justify-end">
              {errorInfo()}
            </div>
          )}

          {/* Card Footer */}
          <div className="flex items-center justify-between mt-auto">
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
