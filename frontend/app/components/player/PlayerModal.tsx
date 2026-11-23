import { UserPlus } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { claimUserProfile, fetchUser } from '~/components/api/api';
import {
  GAME_LABEL,
  GAME_SLUG,
  GAME_TYPES,
  toGameType,
  type GameTypeValue,
} from '~/components/game/constants';
import { PlayerLeagueSummary } from '~/components/player/PlayerLeagueSummary';
import { Badge } from '~/components/ui/badge';
import {
  DotabuffButton,
  PrimaryButton,
  ViewIconButton,
} from '~/components/ui/buttons';
import { InfoDialog } from '~/components/ui/dialogs';
import { useSharedPopover } from '~/components/ui/shared-popover-context';
import { UserAvatar } from '~/components/user/UserAvatar';
import { DisplayName } from '~/components/user/avatar';
import { RolePositions } from '~/components/user/positions';
import { hasAnyPosition } from '~/components/user/positions/hasAnyPosition';
import type { UserType } from '~/components/user/types';
import { User } from '~/components/user/user';
import UserEditModal from '~/components/user/userCard/editModal';
import {
  useScopedEditPermission,
  type EditUserScope,
} from '~/components/user/userCard/editUserSchema';
import { useGameType } from '~/hooks/useGameType';
import { usePlayerPositions } from '~/hooks/usePlayerPositions';
import { getLogger } from '~/lib/logger';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import { isUserEntry } from '~/store/userCacheTypes';
import { useUserStore } from '~/store/userStore';

const log = getLogger('PlayerModal');

interface PlayerModalProps {
  player: UserType;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  leagueId?: number;
  organizationId?: number;
}

export const PlayerModal: React.FC<PlayerModalProps> = ({
  player,
  open,
  onOpenChange,
  leagueId,
  organizationId,
}) => {
  const navigate = useNavigate();
  const currentUser = useUserStore((state) => state.currentUser);
  const setCurrentUser = useUserStore((state) => state.setCurrentUser);

  const { playerModalState } = useSharedPopover();
  const ctx = playerModalState.context;
  const currentOrg = useOrgStore((s) => s.currentOrg);
  const currentLeague = useLeagueStore((s) => s.currentLeague);

  // The page's game only; null (org and global pages) shows every game.
  const gameType = useGameType();

  const editScope = React.useMemo<EditUserScope>(() => {
    // Org context: only trust currentOrg if its pk matches the popover's request.
    if (ctx?.organizationId && currentOrg?.pk === ctx.organizationId) {
      return {
        kind: 'org',
        organization: currentOrg,
        ...(gameType != null ? { gameType } : {}),
      };
    }
    // League context: pk-match guard. Carry the parent organization through if available.
    if (ctx?.leagueId && currentLeague?.pk === ctx.leagueId) {
      return {
        kind: 'league',
        league: currentLeague,
        organization:
          currentOrg && currentLeague.organization?.pk === currentOrg.pk
            ? currentOrg
            : undefined,
        ...(gameType != null ? { gameType } : {}),
      };
    }
    return { kind: 'global' };
  }, [
    gameType,
    ctx?.organizationId,
    ctx?.leagueId,
    currentOrg?.pk,
    currentLeague?.pk,
    currentLeague?.organization?.pk,
    currentOrg,
    currentLeague,
  ]);

  const canEdit = useScopedEditPermission(editScope);

  // Fetch full user data for editing (player prop may have partial data from herodraft)
  const [fullUserData, setFullUserData] = useState<UserType | null>(null);
  const [isLoadingUser, setIsLoadingUser] = useState(false);
  const [isClaiming, setIsClaiming] = useState(false);

  // The `player` prop (signup list, leaderboard row, draft seat) may lack
  // orgUserPk, which dispatchPatch() requires for org- and league-scoped
  // edits; without it Save throws "Org scope requires user.orgUserPk". Look it
  // up from the user cache as userCard.tsx does, via the parent org pk for
  // league scope.
  const cachedUserEntry = useUserCacheStore((s) =>
    player.pk != null ? s.entities[player.pk] : undefined,
  );
  const orgLookupPk =
    editScope.kind === 'org'
      ? editScope.organization.pk
      : editScope.kind === 'league'
        ? (editScope.organization?.pk ?? editScope.league.organization?.pk)
        : (ctx?.organizationId ?? organizationId);
  const orgEntry =
    cachedUserEntry && isUserEntry(cachedUserEntry) && orgLookupPk != null
      ? cachedUserEntry.orgData[orgLookupPk]
      : undefined;
  const orgEntryMmr = gameType != null ? orgEntry?.mmrs[gameType] : undefined;

  const editUser = React.useMemo(() => {
    const base = (fullUserData || player) as UserType;
    const merged =
      orgEntry !== undefined
        ? {
            ...base,
            orgUserPk: orgEntry.id,
            ...(gameType != null
              ? { mmr: orgEntryMmr, mmr_game_type: gameType }
              : {}),
          }
        : base;
    return new User(merged);
  }, [fullUserData, player, orgEntry?.id, orgEntryMmr, gameType]);

  // Can claim if: target HAS steam_account_id (manually added profile with steam identifier),
  // target has NO discordId (can't log in), and current user HAS discordId (can log in).
  // Note: steam_account_id is unique in the database. Claiming merges the profile.
  const canClaimProfile =
    player.steam_account_id &&
    !player.discordId &&
    currentUser?.discordId &&
    currentUser?.pk !== player.pk;

  const statsLeaguePk =
    ctx?.statsLeagueId !== undefined ? ctx.statsLeagueId : leagueId;

  // Fetch full user data when modal opens
  useEffect(() => {
    if (open && player.pk && canEdit && !fullUserData) {
      setIsLoadingUser(true);
      fetchUser(player.pk)
        .then((data) => {
          setFullUserData(data);
          log.debug('Fetched full user data for editing', data);
        })
        .catch((err) => {
          log.error('Failed to fetch full user data', err);
        })
        .finally(() => {
          setIsLoadingUser(false);
        });
    }
  }, [open, player.pk, canEdit]);

  useEffect(() => {
    setFullUserData(null);
  }, [player.pk]);

  const displayPlayer = fullUserData || player;
  const playerName = DisplayName(displayPlayer);
  // Same resolution RolePositions uses, so the wrapper hides exactly when it renders nothing.
  const positions =
    usePlayerPositions(displayPlayer.pk ?? -1) ?? displayPlayer.positions;

  // Context game: that game only. Org scope: every game the cache received.
  const mmrLines: [GameTypeValue, number][] = (() => {
    if (orgEntry) {
      const games = gameType != null ? [gameType] : GAME_TYPES;
      return games.flatMap((g) => {
        const v = orgEntry.mmrs[g];
        return v === undefined ? [] : [[g, v] as [GameTypeValue, number]];
      });
    }
    const flatGame = toGameType(player.mmr_game_type ?? gameType);
    if (!player.mmr || (gameType != null && flatGame !== gameType)) return [];
    return [[flatGame, player.mmr]];
  })();

  const handleViewFullProfile = () => {
    if (displayPlayer.pk) {
      onOpenChange(false);
      navigate(`/user/${displayPlayer.pk}`);
    }
  };

  const handleClaimProfile = async () => {
    if (!player.pk || !currentUser?.pk) return;

    setIsClaiming(true);
    const claim = claimUserProfile(player.pk);
    toast.promise(claim, {
      loading: 'Claiming profile...',
      success: (updatedUser) => {
        // Update current user with merged data
        setCurrentUser(updatedUser);
        onOpenChange(false);
        return `Profile claimed! Your Steam data has been linked.`;
      },
      error: (err) => {
        log.error('Failed to claim profile', err);
        return err?.response?.data?.error || 'Failed to claim profile';
      },
    });

    try {
      await claim;
    } catch {
      // toast.promise already surfaced the failure to the user.
    } finally {
      setIsClaiming(false);
    }
  };

  return (
    <InfoDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Player Profile"
      size="lg"
      showClose={false}
    >
      {/* p-1 keeps the avatar's ring-2 inside the scroll viewport's clip edge */}
      <div className="space-y-4 p-1">
        {/* Header with avatar and name */}
        <div className="flex items-center gap-4">
          <UserAvatar user={displayPlayer} size="xl" border="primary" />
          <div className="flex-1">
            <h2 className="text-xl font-semibold">{playerName}</h2>
            <div className="flex gap-2 mt-1">
              {displayPlayer.is_staff && (
                <Badge className="bg-role-staff text-white">Staff</Badge>
              )}
              {displayPlayer.is_superuser && (
                <Badge className="bg-role-admin text-white">Admin</Badge>
              )}
            </div>
          </div>
          {/* Action buttons */}
          <div className="flex items-center gap-2">
            {canEdit &&
              displayPlayer.pk &&
              (isLoadingUser ? (
                <span className="text-xs text-muted-foreground">
                  Loading...
                </span>
              ) : (
                <UserEditModal user={editUser} scope={editScope} />
              ))}
            {displayPlayer.pk && (
              <ViewIconButton
                onClick={handleViewFullProfile}
                tooltip="View Full Profile"
              />
            )}
          </div>
        </div>

        {/* Player info */}
        <div className="space-y-2 text-sm">
          {displayPlayer.username && (
            <div>
              <span className="font-semibold">Username:</span>{' '}
              {/* eslint-disable-next-line draftforge/use-display-name -- labelled Username field shows the account handle */}
              {displayPlayer.username}
            </div>
          )}
          {displayPlayer.nickname && (
            <div>
              <span className="font-semibold">Nickname:</span>{' '}
              {/* eslint-disable-next-line draftforge/use-display-name -- labelled Nickname field shows the site nickname itself */}
              {displayPlayer.nickname}
            </div>
          )}
          {mmrLines.map(([g, value]) => (
            <div key={g} data-testid={`player-modal-org-mmr-${GAME_SLUG[g]}`}>
              <span className="font-semibold">{GAME_LABEL[g]} org MMR:</span>{' '}
              {value || '\u2014'}
            </div>
          ))}
          {/* Positions - pt-1 pl-1 accommodates the absolute positioned rank badges */}
          {hasAnyPosition(positions) && (
            <div className="pt-1 pl-1" data-testid="player-modal-positions">
              <RolePositions user={displayPlayer} />
            </div>
          )}
          {displayPlayer.steam_account_id && (
            <div>
              <span className="font-semibold">Friend ID:</span>{' '}
              {displayPlayer.steam_account_id}
            </div>
          )}
        </div>

        {/* League Stats (if context provided) */}
        {statsLeaguePk && player.pk ? (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-muted-foreground">
              League Stats
            </h3>
            <PlayerLeagueSummary leaguePk={statsLeaguePk} userId={player.pk} />
          </div>
        ) : null}

        {/* Organization Stats placeholder (if context provided) */}
        {organizationId && !statsLeaguePk && (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-muted-foreground">
              Organization Stats
            </h3>
            <div className="text-sm text-muted-foreground">
              Organization stats coming soon
            </div>
          </div>
        )}

        {/* Action buttons */}
        <div className="pt-2 flex gap-2">
          <DotabuffButton
            steamAccountId={displayPlayer.steam_account_id}
            responsive={false}
            className="flex-1"
          />

          {/* Claim Profile button */}
          {canClaimProfile && (
            <PrimaryButton
              size="sm"
              className="flex-1"
              onClick={handleClaimProfile}
              disabled={isClaiming}
              data-testid={`claim-profile-modal-btn-${displayPlayer.pk}`}
            >
              <UserPlus />
              {isClaiming ? 'Claiming...' : 'Claim Profile'}
            </PrimaryButton>
          )}
        </div>
      </div>
    </InfoDialog>
  );
};
