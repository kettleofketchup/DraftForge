import { useCallback, useMemo, useState } from 'react';
import type { TeamType } from '~/components/tournament/types';
import type { UserType } from '~/components/user/types';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import { TeamTable } from '~/components/team/teamTable/teamTable';

interface CaptainPopoverProps {
  captain: UserType;
  team: TeamType;
  children: React.ReactNode;
}

export const CaptainPopover: React.FC<CaptainPopoverProps> = ({
  captain,
  team,
  children,
}) => {
  const [open, setOpen] = useState(false);

  const avgMMR = useMemo(() => {
    if (!team.members || team.members.length === 0) return 0;
    const total = team.members.reduce(
      (sum: number, m: UserType) => sum + (m.mmr || 0),
      0
    );
    return Math.round(total / team.members.length);
  }, [team.members]);

  const teamName = team.name || `${captain.nickname || captain.username}'s Team`;
  const hasMembers = team.members && team.members.length > 0;

  const handleMouseEnter = useCallback(() => {
    setOpen(true);
  }, []);

  const handleMouseLeave = useCallback(() => {
    setOpen(false);
  }, []);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      setOpen((prev) => !prev);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  }, []);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <span
          className="cursor-pointer"
          role="button"
          tabIndex={0}
          aria-label={`View ${teamName} roster`}
          aria-expanded={open}
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
          onKeyDown={handleKeyDown}
        >
          {children}
        </span>
      </PopoverTrigger>
      <PopoverContent
        className="w-80 p-0"
        onOpenAutoFocus={(e) => e.preventDefault()}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-3 border-b">
          <span className="font-medium">{teamName}</span>
          {hasMembers && (
            <span className="text-sm text-muted-foreground">
              Avg: {avgMMR.toLocaleString()} MMR
            </span>
          )}
        </div>

        {/* Team Table or Empty State */}
        <div className="max-h-64 overflow-y-auto">
          {hasMembers ? (
            <TeamTable team={team} />
          ) : (
            <div className="p-4 text-center text-muted-foreground">
              No players drafted yet
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
};
