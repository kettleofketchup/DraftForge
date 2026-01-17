import { useCallback, useRef, useState } from 'react';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import { RolePositions } from '~/components/user/positions';
import type { UserType } from '~/components/user/types';
import { AvatarUrl } from '~/index';
import { PlayerModal } from './PlayerModal';

interface PlayerPopoverProps {
  player: UserType;
  children: React.ReactNode;
}

export const PlayerPopover: React.FC<PlayerPopoverProps> = ({
  player,
  children,
}) => {
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const hoverIntentRef = useRef<NodeJS.Timeout | null>(null);
  const isHoveringRef = useRef(false);
  const playerName = player.nickname || player.username || 'Unknown';

  const handleClick = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (hoverIntentRef.current) {
      clearTimeout(hoverIntentRef.current);
    }
    setPopoverOpen(false);
    setModalOpen(true);
  }, []);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      setPopoverOpen(false);
      setModalOpen(true);
    } else if (e.key === 'Escape') {
      setPopoverOpen(false);
    }
  }, []);

  const handleMouseEnter = useCallback(() => {
    isHoveringRef.current = true;
    // Small delay to prevent accidental triggers
    hoverIntentRef.current = setTimeout(() => {
      if (isHoveringRef.current) {
        setPopoverOpen(true);
      }
    }, 50);
  }, []);

  const handleMouseLeave = useCallback(() => {
    isHoveringRef.current = false;
    if (hoverIntentRef.current) {
      clearTimeout(hoverIntentRef.current);
    }
    setPopoverOpen(false);
  }, []);

  return (
    <>
      <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
        <PopoverTrigger asChild>
          <span
            className="cursor-pointer"
            role="button"
            tabIndex={0}
            aria-label={`View profile for ${playerName}`}
            aria-expanded={popoverOpen}
            onClick={handleClick}
            onKeyDown={handleKeyDown}
            onMouseEnter={handleMouseEnter}
            onMouseLeave={handleMouseLeave}
          >
            {children}
          </span>
        </PopoverTrigger>
        <PopoverContent
          className="w-56 p-3"
          onOpenAutoFocus={(e) => e.preventDefault()}
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
        >
          <div className="space-y-2">
            {/* Header with avatar and name */}
            <div className="flex items-center gap-3">
              <img
                src={AvatarUrl(player)}
                alt={`${playerName}'s avatar`}
                className="w-12 h-12 rounded-full"
              />
              <div>
                <p className="font-medium">{playerName}</p>
                {player.mmr && (
                  <p className="text-sm text-muted-foreground">
                    MMR: {player.mmr}
                  </p>
                )}
              </div>
            </div>

            {/* Positions */}
            <RolePositions user={player} />

            {/* Click hint */}
            <p className="text-xs text-muted-foreground text-center pt-1">
              Click for full profile
            </p>
          </div>
        </PopoverContent>
      </Popover>

      <PlayerModal
        player={player}
        open={modalOpen}
        onOpenChange={setModalOpen}
      />
    </>
  );
};
