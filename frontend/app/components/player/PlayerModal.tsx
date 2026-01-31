import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { Badge } from '~/components/ui/badge';
import { ViewIconButton } from '~/components/ui/buttons';
import { InfoDialog } from '~/components/ui/dialogs';
import { RolePositions } from '~/components/user/positions';
import type { UserType } from '~/components/user/types';
import { User } from '~/components/user/user';
import UserEditModal from '~/components/user/userCard/editModal';
import { UserAvatar } from '~/components/user/UserAvatar';
import { useUserStore } from '~/store/userStore';
import { LeagueStatsCard } from '~/components/user/LeagueStatsCard';
import { useUserLeagueStats } from '~/features/leaderboard/queries';
import { fetchUser } from '~/components/api/api';
import { getLogger } from '~/lib/logger';

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
  const canEdit = currentUser?.is_staff || currentUser?.is_superuser;

  // Fetch full user data for editing (player prop may have partial data from herodraft)
  const [fullUserData, setFullUserData] = useState<UserType | null>(null);
  const [isLoadingUser, setIsLoadingUser] = useState(false);

  // Fetch league stats if leagueId is provided
  // TODO: Update useUserLeagueStats to accept leagueId parameter when backend supports it
  const { data: leagueStats, isLoading: isLoadingStats } = useUserLeagueStats(
    leagueId && player.pk ? player.pk : null
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

  const goToDotabuff = () => {
    if (!displayPlayer.steamid) return '#';
    return `https://www.dotabuff.com/players/${encodeURIComponent(String(displayPlayer.steamid))}`;
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
                <UserEditModal user={new User(fullUserData || displayPlayer)} />
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
          {displayPlayer.steamid && (
            <div>
              <span className="font-semibold">Steam ID:</span> {displayPlayer.steamid}
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

        {/* Dotabuff link */}
        {displayPlayer.steamid && (
          <div className="pt-2">
            <a
              className="flex items-center justify-center btn btn-sm btn-outline w-full"
              href={goToDotabuff()}
              target="_blank"
              rel="noopener noreferrer"
            >
              <img
                src="https://cdn.brandfetch.io/idKrze_WBi/w/96/h/96/theme/dark/logo.png?c=1dxbfHSJFAPEGdCLU4o5B"
                alt="Dotabuff Logo"
                className="w-4 h-4 mr-2"
              />
              Dotabuff Profile
            </a>
          </div>
        )}
      </div>
    </InfoDialog>
  );
};
