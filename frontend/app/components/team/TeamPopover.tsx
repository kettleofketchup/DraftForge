import { memo, useCallback, useMemo, useRef, useState } from 'react';
import type { TeamType } from '~/components/tournament/types';
import type { UserType } from '~/components/user/types';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import { PlayerPopover } from '~/components/player';
import { TeamModal } from './TeamModal';
import { RolePositions } from '~/components/user/positions';
import { AvatarUrl } from '~/index';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '~/components/ui/table';

interface TeamPopoverProps {
  team: TeamType;
  children: React.ReactNode;
}

// Memoized row component to prevent re-renders
const TeamMemberRow = memo(({
  member,
  isCaptain,
}: {
  member: UserType;
  isCaptain: boolean;
}) => (
  <TableRow>
    <TableCell>
      <PlayerPopover player={member}>
        <div className="flex items-center gap-2 cursor-pointer hover:text-primary transition-colors">
          <img
            src={AvatarUrl(member)}
            alt={member.username}
            className="w-8 h-8 rounded-full hover:ring-2 hover:ring-primary transition-all"
          />
          <span className="font-medium">
            {member.nickname || member.username}
          </span>
          {isCaptain && (
            <span className="text-xs text-primary">(C)</span>
          )}
        </div>
      </PlayerPopover>
    </TableCell>
    <TableCell className="text-right">
      {member.mmr?.toLocaleString() || 'N/A'}
    </TableCell>
    <TableCell>
      <RolePositions user={member} />
    </TableCell>
  </TableRow>
));
TeamMemberRow.displayName = 'TeamMemberRow';

export const TeamPopover: React.FC<TeamPopoverProps> = ({
  team,
  children,
}) => {
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const hoverIntentRef = useRef<NodeJS.Timeout | null>(null);
  const isHoveringRef = useRef(false);

  const captain = team.captain;

  const avgMMR = useMemo(() => {
    if (!team.members || team.members.length === 0) return 0;
    const total = team.members.reduce(
      (sum: number, m: UserType) => sum + (m.mmr || 0),
      0
    );
    return Math.round(total / team.members.length);
  }, [team.members]);

  const sortedMembers = useMemo(() => {
    if (!team.members) return [];
    return [...team.members].sort((a: UserType, b: UserType) => {
      if (!a.mmr && !b.mmr) return 0;
      if (!a.mmr) return 1;
      if (!b.mmr) return -1;
      return b.mmr - a.mmr;
    });
  }, [team.members]);

  const teamName = team.name || `${captain?.nickname || captain?.username || 'Unknown'}'s Team`;
  const hasMembers = team.members && team.members.length > 0;

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

  return (
    <>
      <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
        <PopoverTrigger asChild>
          <span
            className="cursor-pointer h-full"
            role="button"
            tabIndex={0}
            aria-label={`View ${teamName} roster`}
            aria-expanded={popoverOpen}
            onMouseEnter={handleMouseEnter}
            onMouseLeave={handleMouseLeave}
            onClick={handleClick}
            onKeyDown={handleKeyDown}
          >
            {children}
          </span>
        </PopoverTrigger>
        <PopoverContent
          className="w-[640px] p-0"
          onOpenAutoFocus={(e) => e.preventDefault()}
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
        >
          {/* Header */}
          <div className="flex items-center justify-between p-3 border-b">
            <span className="font-medium">{teamName}</span>
            {hasMembers && (
              <span className="text-sm text-muted-foreground">
                {team.members?.length} players | Avg: {avgMMR.toLocaleString()} MMR
              </span>
            )}
          </div>

          {/* Team Table or Empty State */}
          <div className="max-h-80 overflow-y-auto">
            {hasMembers ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Player</TableHead>
                    <TableHead className="text-right">MMR</TableHead>
                    <TableHead>Positions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sortedMembers.map((member: UserType) => (
                    <TeamMemberRow
                      key={member.pk}
                      member={member}
                      isCaptain={captain?.pk === member.pk}
                    />
                  ))}
                </TableBody>
              </Table>
            ) : (
              <div className="p-4 text-center text-muted-foreground">
                No players drafted yet
              </div>
            )}
          </div>

          {/* Click hint */}
          <div className="p-2 border-t text-center text-xs text-muted-foreground">
            Click for full view
          </div>
        </PopoverContent>
      </Popover>

      {/* Team Modal */}
      {captain && (
        <TeamModal
          team={team}
          captain={captain}
          open={modalOpen}
          onOpenChange={setModalOpen}
        />
      )}
    </>
  );
};
