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
import { useOrgStore } from '~/store/orgStore';
import { useUserStore } from '~/store/userStore';
import { RolePositions } from './positions';
import { UserRemoveButton } from './userCard/deleteButton';
import UserEditModal from './userCard/editModal';
import type { EditUserScope } from './userCard/editUserSchema';
import { LoginAsUserButton } from './userCard/LoginAsUserButton';

/** Returns true if the user has rated any role > 0. */
function hasAnyPosition(user: UserClassType | UserType): boolean {
  const p = user.positions;
  if (!p) return false;
  return (p.carry ?? 0) > 0
    || (p.mid ?? 0) > 0
    || (p.offlane ?? 0) > 0
    || (p.soft_support ?? 0) > 0
    || (p.hard_support ?? 0) > 0;
}
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
    const currentOrg = useOrgStore((state) => state.currentOrg);
    const { openPlayerModal } = useSharedPopover();

    const orgEntry = isUserEntry(user) && organizationId ? user.orgData[organizationId] : undefined;
    const mmr = isUserEntry(user)
      ? (organizationId ? orgEntry?.mmr : undefined)
      : user.mmr;

    const editScope = React.useMemo<EditUserScope>(
      () =>
        orgEntry && currentOrg
          ? { kind: 'org', organization: currentOrg }
          : { kind: 'global' },
      [orgEntry?.id, currentOrg?.pk],
    );

    const handleViewProfile = () => {
      openPlayerModal(user, { organizationId: currentOrg?.pk, leagueId });
    };

    useEffect(() => {
      if (!user.pk) {
        log.error('User does not have a primary key (pk)');
        getUsers();
      }
    }, [user.pk, getUsers]);

    const hasError = () => {
      // Only show MMR error when viewing in an org context
      if (organizationId && !mmr) {
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
      if (!user.steam_account_id) return null;
      const url = `https://www.dotabuff.com/players/${user.steam_account_id}`;
      return (
        <a
          className="inline-flex items-center gap-1 px-3 py-1 rounded-md text-sm font-medium
            bg-base-200 border border-border text-foreground
            shadow-md shadow-black/30 border-b-4 border-b-violet-700/60
            transform-gpu transition-transform duration-150
            hover:scale-105 hover:bg-base-100
            active:translate-y-0.5 active:border-b-0
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          // Native title — zero React cost (vs. Radix Tooltip which adds
          // 4 components + a portal mount per hovered card).
          title="View Dotabuff profile"
        >
          <img
            src="https://cdn.brandfetch.io/idKrze_WBi/w/96/h/96/theme/dark/logo.png?c=1dxbfHSJFAPEGdCLU4o5B"
            alt=""
            aria-hidden="true"
            className="w-4 h-4"
          />
          <span className="hidden sm:inline">Dotabuff</span>
        </a>
      );
    };

    // Show "Claim Profile" button when:
    // - Target user HAS Friend ID (manually added profile with steam identifier)
    // - Target user has NO Discord ID (manually added, can't log in)
    // - Current user HAS Discord ID (logged in, can claim)
    // - Current user either has NO Friend ID or has the SAME Friend ID as target
    // - Current user is not this user
    // Note: steam_account_id is unique in the database. Claiming merges the profile.
    const canClaimProfile =
      user.steam_account_id &&
      !user.discordId &&
      currentUser?.discordId &&
      (!currentUser?.steam_account_id || currentUser.steam_account_id === user.steam_account_id) &&
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
          {organizationId && !mmr && (
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
        // min-w-0 is the critical fix for grid overflow: by default a grid
        // item's min-width is `auto` (= intrinsic content width), so when
        // children have content wider than the 1fr track, the cell EXPANDS
        // past the grid's column width and pushes neighbors / overflows.
        // min-w-0 forces the cell to respect 1fr, letting overflow-hidden
        // on the inner card actually clip overflow.
        // overflow-visible lets the motion.div's hover scale: 1.02 paint
        // beyond the wrapper's box without being clipped.
        // [contain:layout_style] is CSS containment WITHOUT `paint` or
        // `size` — the browser isolates this card's layout/style work
        // (so hover repaints don't ripple through neighbors), without
        // clipping the hover-scale paint. Replaces the older
        // [content-visibility:auto] which clipped the transform.
        className="flex w-full min-w-0 py-2 items-stretch overflow-visible
          [contain:layout_style]"
      >
        <div
          key={`usercard:${getKeyName()} basediv`}
          // Pure CSS hover scale (no Framer Motion). transform-gpu promotes
          // to its own compositor layer so scroll-time hover scaling doesn't
          // reflow neighbors. transition-transform is short so the hover
          // feels instant. Replaces the previous motion.div which paid the
          // full Framer animation-pipeline tax for every visible card on
          // every scroll-triggered remount.
          className="flex flex-col gap-2 card card-compact bg-base-300 rounded-2xl
            w-full min-w-0 p-2 overflow-hidden transform-gpu
            transition-transform duration-150 hover:scale-[1.02]
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
              {/* UserEditModal performs its own scope-aware permission check
                  via useScopedEditPermission and renders null when the current
                  user lacks edit rights for the resolved scope. */}
              <UserEditModal
                user={
                  new User(
                    isUserEntry(user) && orgEntry
                      ? { ...user, mmr: orgEntry.mmr, orgUserPk: orgEntry.id }
                      : user,
                  )
                }
                scope={editScope}
              />
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
              {hasAnyPosition(user) && (
                <Item size="sm" variant="muted" className="!p-1.5 w-full">
                  <ItemContent className="!gap-1 items-center w-full">
                    <ItemTitle className="!text-xs text-muted-foreground">Positions</ItemTitle>
                    <RolePositions user={user} compact />
                  </ItemContent>
                </Item>
              )}
              {/* MMR row — only meaningful inside an org or league context.
                  On the global /users grid neither id is provided, so the
                  whole row is hidden (there's no "base" MMR concept).
                  flex-wrap so a single MMR tile takes the full width when
                  the other isn't shown. */}
              {(organizationId || leagueId) && (
                <div className="flex flex-wrap gap-1 w-full">
                  {organizationId && (
                    <Item size="sm" variant="muted" className="!p-1 flex-1 min-w-0">
                      <ItemContent className="!gap-0 items-center min-w-0">
                        <ItemTitle className="!text-xs text-muted-foreground">Org MMR</ItemTitle>
                        <span className="text-sm font-semibold">{mmr ?? '?'}</span>
                      </ItemContent>
                    </Item>
                  )}
                  {leagueId && (
                    <Item size="sm" variant="muted" className="!p-1 flex-1 min-w-0">
                      <ItemContent className="!gap-0 items-center min-w-0">
                        <ItemTitle className="!text-xs text-muted-foreground">League MMR</ItemTitle>
                        <span className="text-sm font-semibold">?</span>
                      </ItemContent>
                    </Item>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* User info row — flex-wrap so each tile takes a fair share of
              the card width: alone it spans full width, two share, three
              wrap to two rows. flex-1 + min-w-0 lets the inner text
              truncate cleanly when the card is narrow. */}
          <div className="flex flex-wrap gap-1">
            {user.username && (
              <Item size="sm" variant="muted" className="!p-1 flex-1 min-w-0 basis-[calc(50%-0.125rem)]">
                <ItemContent className="!gap-0 min-w-0">
                  <ItemTitle className="!text-xs text-muted-foreground">Username</ItemTitle>
                  <span className="text-sm truncate">{user.username}</span>
                </ItemContent>
              </Item>
            )}
            {user.nickname && user.nickname !== user.username && (
              <Item size="sm" variant="muted" className="!p-1 flex-1 min-w-0 basis-[calc(50%-0.125rem)]">
                <ItemContent className="!gap-0 min-w-0">
                  <ItemTitle className="!text-xs text-muted-foreground">Nickname</ItemTitle>
                  <span className="text-sm truncate">{user.nickname}</span>
                </ItemContent>
              </Item>
            )}
            {user.steam_account_id && (
              <Item size="sm" variant="muted" className="!p-1 flex-1 min-w-0 basis-[calc(50%-0.125rem)]">
                <ItemContent className="!gap-0 min-w-0">
                  <ItemTitle className="!text-xs text-muted-foreground">Friend ID</ItemTitle>
                  <span className="text-sm truncate">{user.steam_account_id}</span>
                </ItemContent>
              </Item>
            )}
          </div>

          {/* Error info row */}
          {((organizationId && !mmr) || !user.positions) && (
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
        </div>
      </div>
    );
  },
);
