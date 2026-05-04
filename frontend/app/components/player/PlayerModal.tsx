import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { claimUserProfile, fetchUser } from '~/components/api/api';
import { Badge } from '~/components/ui/badge';
import { DotabuffButton, ViewIconButton } from '~/components/ui/buttons';
import { InfoDialog } from '~/components/ui/dialogs';
import { useSharedPopover } from '~/components/ui/shared-popover-context';
import { LeagueStatsCard } from '~/components/user/LeagueStatsCard';
import { RolePositions } from '~/components/user/positions';
import type { UserType } from '~/components/user/types';
import { User } from '~/components/user/user';
import UserEditModal from '~/components/user/userCard/editModal';
import type { EditUserScope } from '~/components/user/userCard/editUserSchema';
import { UserAvatar } from '~/components/user/UserAvatar';
import { useUserLeagueStats } from '~/features/leaderboard/queries';
import { getLogger } from '~/lib/logger';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { isUserEntry } from '~/store/userCacheTypes';
import { useUserCacheStore } from '~/store/userCacheStore';
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
  const canEdit = currentUser?.is_staff || currentUser?.is_superuser;

  const { playerModalState } = useSharedPopover();
  const ctx = playerModalState.context;
  const currentOrg = useOrgStore((s) => s.currentOrg);
  const currentLeague = useLeagueStore((s) => s.currentLeague);

  const editScope = React.useMemo<EditUserScope>(() => {
    // Org context: only trust currentOrg if its pk matches the popover's request.
    if (ctx?.organizationId && currentOrg?.pk === ctx.organizationId) {
      return { kind: 'org', organization: currentOrg };
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
      };
    }
    return { kind: 'global' };
  }, [
    ctx?.organizationId,
    ctx?.leagueId,
    currentOrg?.pk,
    currentLeague?.pk,
    currentLeague?.organization?.pk,
    currentOrg,
    currentLeague,
  ]);

  // Fetch full user data for editing (player prop may have partial data from herodraft)
  const [fullUserData, setFullUserData] = useState<UserType | null>(null);
  const [isLoadingUser, setIsLoadingUser] = useState(false);
  const [isClaiming, setIsClaiming] = useState(false);

  // PlayerModal can be opened with a `player` prop that lacks orgUserPk
  // (it comes from a signup list, a leaderboard row, or a draft seat).
  // For org-scoped edits, dispatchPatch() requires user.orgUserPk; without
  // it the Save button throws "Org scope requires user.orgUserPk". Look the
  // OrgUser pk up from the user cache the same way userCard.tsx does.
  //
  // League scope is also reachable from PlayerModal (editUserSchema.ts:112-116
  // requires orgUserPk for league-scoped edits too), so we widen the lookup to
  // cover both cases using the parent org pk.
  const cachedUserEntry = useUserCacheStore((s) =>
    player.pk != null ? s.entities[player.pk] : undefined,
  );
  const orgLookupPk =
    editScope.kind === 'org'
      ? editScope.organization.pk
      : editScope.kind === 'league'
        ? (editScope.organization?.pk ?? editScope.league.organization?.pk)
        : undefined;
  const orgEntry =
    cachedUserEntry && isUserEntry(cachedUserEntry) && orgLookupPk != null
      ? cachedUserEntry.orgData[orgLookupPk]
      : undefined;

  const editUser = React.useMemo(() => {
    const base = (fullUserData || player) as UserType;
    const merged =
      orgEntry !== undefined
        ? { ...base, mmr: orgEntry.mmr, orgUserPk: orgEntry.id }
        : base;
    return new User(merged);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fullUserData, player, orgEntry?.id, orgEntry?.mmr]);

  // Can claim if: target HAS steam_account_id (manually added profile with steam identifier),
  // target has NO discordId (can't log in), and current user HAS discordId (can log in).
  // Note: steam_account_id is unique in the database. Claiming merges the profile.
  const canClaimProfile =
    player.steam_account_id &&
    !player.discordId &&
    currentUser?.discordId &&
    currentUser?.pk !== player.pk;

  const { data: leagueStats, isLoading: isLoadingStats } = useUserLeagueStats(
    leagueId && player.pk ? player.pk : null,
    leagueId
  );

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

  // Reset full user data when player changes
  useEffect(() => {
    setFullUserData(null);
  }, [player.pk]);

  // Use full data if available, otherwise fall back to partial player data
  const displayPlayer = fullUserData || player;
  const playerName = displayPlayer.nickname || displayPlayer.username || 'Unknown';

  const handleViewFullProfile = () => {
    if (displayPlayer.pk) {
      onOpenChange(false);
      navigate(`/user/${displayPlayer.pk}`);
    }
  };

  const handleClaimProfile = async () => {
    if (!player.pk || !currentUser?.pk) return;

    setIsClaiming(true);
    toast.promise(
      claimUserProfile(player.pk),
      {
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
      }
    ).finally(() => setIsClaiming(false));
  };

  return (
    <InfoDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Player Profile"
      size="lg"
      showClose={false}
    >
      {/* User Card Section */}
      <div className="space-y-4">
        {/* Header with avatar and name */}
        <div className="flex items-center gap-4">
          <UserAvatar user={displayPlayer} size="xl" border="primary" />
          <div className="flex-1">
            <h2 className="text-xl font-semibold">{playerName}</h2>
            <div className="flex gap-2 mt-1">
              {displayPlayer.is_staff && (
                <Badge className="bg-blue-700 text-white">Staff</Badge>
              )}
              {displayPlayer.is_superuser && (
                <Badge className="bg-red-700 text-white">Admin</Badge>
              )}
            </div>
          </div>
          {/* Action buttons */}
          <div className="flex items-center gap-2">
            {canEdit && displayPlayer.pk && (
              isLoadingUser ? (
                <span className="text-xs text-muted-foreground">Loading...</span>
              ) : (
                <UserEditModal user={editUser} scope={editScope} />
              )
            )}
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
              <span className="font-semibold">Username:</span> {displayPlayer.username}
            </div>
          )}
          {displayPlayer.nickname && (
            <div>
              <span className="font-semibold">Nickname:</span> {displayPlayer.nickname}
            </div>
          )}
          {displayPlayer.mmr && (
            <div>
              <span className="font-semibold">MMR:</span> {displayPlayer.mmr}
            </div>
          )}
          {/* Positions - pt-1 pl-1 accommodates the absolute positioned rank badges */}
          <div className="pt-1 pl-1">
            <RolePositions user={displayPlayer} />
          </div>
          {displayPlayer.steam_account_id && (
            <div>
              <span className="font-semibold">Friend ID:</span> {displayPlayer.steam_account_id}
            </div>
          )}
        </div>

        {/* League Stats (if context provided) */}
        {leagueId && (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-muted-foreground">League Stats</h3>
            {isLoadingStats ? (
              <div className="text-sm text-muted-foreground">Loading stats...</div>
            ) : leagueStats ? (
              <LeagueStatsCard
                stats={leagueStats}
                baseMmr={leagueStats.base_mmr}
                leagueMmr={leagueStats.league_mmr}
                compact
              />
            ) : (
              <div className="text-sm text-muted-foreground">No league stats available</div>
            )}
          </div>
        )}

        {/* Organization Stats placeholder (if context provided) */}
        {organizationId && !leagueId && (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-muted-foreground">Organization Stats</h3>
            <div className="text-sm text-muted-foreground">Organization stats coming soon</div>
          </div>
        )}

        {/* Action buttons */}
        <div className="pt-2 flex gap-2">
          {/* Dotabuff link */}
          <DotabuffButton
            steamAccountId={displayPlayer.steam_account_id}
            responsive={false}
            className="flex-1"
          />

          {/* Claim Profile button */}
          {canClaimProfile && (
            <button
              className="flex items-center justify-center btn btn-sm btn-primary flex-1 gap-1"
              onClick={handleClaimProfile}
              disabled={isClaiming}
              data-testid={`claim-profile-modal-btn-${displayPlayer.pk}`}
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <line x1="19" x2="19" y1="8" y2="14" />
                <line x1="22" x2="16" y1="11" y2="11" />
              </svg>
              {isClaiming ? 'Claiming...' : 'Claim Profile'}
            </button>
          )}
        </div>
      </div>
    </InfoDialog>
  );
};
