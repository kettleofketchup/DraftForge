import { useEffect, useState } from 'react';
import { Badge } from '~/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { RolePositions } from '~/components/user/positions';
import type { UserType } from '~/components/user/types';
import { User } from '~/components/user/user';
import UserEditModal from '~/components/user/userCard/editModal';
import { AvatarUrl } from '~/index';
import { useUserStore } from '~/store/userStore';
import { PlayerUnderConstruction } from './PlayerUnderConstruction';
import { fetchUser } from '~/components/api/api';
import { getLogger } from '~/lib/logger';

const log = getLogger('PlayerModal');

interface PlayerModalProps {
  player: UserType;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const PlayerModal: React.FC<PlayerModalProps> = ({
  player,
  open,
  onOpenChange,
}) => {
  const currentUser = useUserStore((state) => state.currentUser);
  const canEdit = currentUser?.is_staff || currentUser?.is_superuser;

  // Fetch full user data for editing (player prop may have partial data from herodraft)
  const [fullUserData, setFullUserData] = useState<UserType | null>(null);
  const [isLoadingUser, setIsLoadingUser] = useState(false);

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

  const goToDotabuff = () => {
    if (!displayPlayer.steamid) return '#';
    return `https://www.dotabuff.com/players/${encodeURIComponent(String(displayPlayer.steamid))}`;
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Player Profile</DialogTitle>
        </DialogHeader>

        {/* User Card Section */}
        <div className="space-y-4">
          {/* Header with avatar and name */}
          <div className="flex items-center gap-4">
            <img
              src={AvatarUrl(displayPlayer)}
              alt={`${playerName}'s avatar`}
              className="w-16 h-16 rounded-full border border-primary"
            />
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
            {canEdit && displayPlayer.pk && (
              isLoadingUser ? (
                <span className="text-xs text-muted-foreground">Loading...</span>
              ) : (
                <UserEditModal user={new User(fullUserData || displayPlayer)} />
              )
            )}
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
            <RolePositions user={displayPlayer} />
            {displayPlayer.steamid && (
              <div>
                <span className="font-semibold">Steam ID:</span> {displayPlayer.steamid}
              </div>
            )}
          </div>

          {/* Dotabuff link */}
          {displayPlayer.steamid && (
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
          )}

          {/* Extended Profile (Under Construction) */}
          <PlayerUnderConstruction playerName={playerName} />
        </div>
      </DialogContent>
    </Dialog>
  );
};
