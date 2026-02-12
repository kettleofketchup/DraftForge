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
import { isUserEntry } from '~/store/userCacheTypes';
import { PlayerRemoveButton } from '~/pages/tournament/tabs/players/playerRemoveButton';
import { useUserStore } from '~/store/userStore';
import { RolePositions } from './positions';
import { UserRemoveButton } from './userCard/deleteButton';
import UserEditModal from './userCard/editModal';
import { LoginAsUserButton } from './userCard/LoginAsUserButton';
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

    const mmr = isUserEntry(user)
      ? (organizationId ? user.orgData[organizationId]?.mmr : undefined)
      : user.mmr;

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
      if (!mmr) {
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
      if (!user.steamid) return null;
      return (
        <a
          className="btn btn-sm btn-outline gap-1"
          href={goToDotabuff()}
          target="_blank"
          rel="noopener noreferrer"
          title="View Dotabuff Profile"
        >
          <img
            src="https://cdn.brandfetch.io/idKrze_WBi/w/96/h/96/theme/dark/logo.png?c=1dxbfHSJFAPEGdCLU4o5B"
            alt="Dotabuff"
            className="w-4 h-4"
          />
          <span className="hidden sm:inline">Dotabuff</span>
        </a>
      );
    };

    // Show "Claim Profile" button when:
    // - Target user HAS Steam ID (manually added profile with steam identifier)
    // - Target user has NO Discord ID (manually added, can't log in)
    // - Current user HAS Discord ID (logged in, can claim)
    // - Current user either has NO Steam ID or has the SAME Steam ID as target
    // - Current user is not this user
    // Note: steamid is unique in the database. Claiming merges the profile.
    const canClaimProfile =
      user.steamid &&
      !user.discordId &&
      currentUser?.discordId &&
      (!currentUser?.steamid || currentUser.steamid === user.steamid) &&
      currentUser?.pk !== user.pk;

    const claimProfileButton = () => {
      if (!canClaimProfile) return null;
      return (
        <button
          className="btn btn-sm btn-primary gap-1"
          onClick={handleViewProfile}
          title="Link your Steam account to this profile"
          data-testid={`claim-profile-btn-${user.pk}`}
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <line x1="19" x2="19" y1="8" y2="14" />
            <line x1="22" x2="16" y1="11" y2="11" />
          </svg>
          <span>Claim</span>
        </button>
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
          {!mmr && (
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
              <LoginAsUserButton user={user} />
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
                    <span className="text-sm font-semibold">{mmr ?? '?'}</span>
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
          {(!mmr || !user.positions) && (
            <div className="flex justify-end">
              {errorInfo()}
            </div>
          )}

          {/* Card Footer */}
          <div className="flex items-center justify-between gap-2 mt-auto">
            {/* Dotabuff / Claim - bottom left */}
            <div className="flex gap-1 flex-shrink-0">
              {userDotabuff()}
              {claimProfileButton()}
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
