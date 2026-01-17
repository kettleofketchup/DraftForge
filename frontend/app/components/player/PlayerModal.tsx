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
  const playerName = player.nickname || player.username || 'Unknown';

  const goToDotabuff = () => {
    if (!player.steamid) return '#';
    return `https://www.dotabuff.com/players/${encodeURIComponent(String(player.steamid))}`;
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
              src={AvatarUrl(player)}
              alt={`${playerName}'s avatar`}
              className="w-16 h-16 rounded-full border border-primary"
            />
            <div className="flex-1">
              <h2 className="text-xl font-semibold">{playerName}</h2>
              <div className="flex gap-2 mt-1">
                {player.is_staff && (
                  <Badge className="bg-blue-700 text-white">Staff</Badge>
                )}
                {player.is_superuser && (
                  <Badge className="bg-red-700 text-white">Admin</Badge>
                )}
              </div>
            </div>
            {canEdit && player.pk && <UserEditModal user={new User(player)} />}
          </div>

          {/* Player info */}
          <div className="space-y-2 text-sm">
            {player.username && (
              <div>
                <span className="font-semibold">Username:</span> {player.username}
              </div>
            )}
            {player.nickname && (
              <div>
                <span className="font-semibold">Nickname:</span> {player.nickname}
              </div>
            )}
            {player.mmr && (
              <div>
                <span className="font-semibold">MMR:</span> {player.mmr}
              </div>
            )}
            <RolePositions user={player} />
            {player.steamid && (
              <div>
                <span className="font-semibold">Steam ID:</span> {player.steamid}
              </div>
            )}
          </div>

          {/* Dotabuff link */}
          {player.steamid && (
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
