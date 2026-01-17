import { useMemo } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { RolePositions } from '~/components/user/positions';
import type { TeamType } from '~/components/tournament/types';
import type { UserType } from '~/components/user/types';
import { PlayerPopover } from '~/components/player';
import { AvatarUrl } from '~/index';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '~/components/ui/table';

interface TeamModalProps {
  team: TeamType;
  captain: UserType;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const TeamModal: React.FC<TeamModalProps> = ({
  team,
  captain,
  open,
  onOpenChange,
}) => {
  const teamName = team.name || `${captain.nickname || captain.username}'s Team`;
  const hasMembers = team.members && team.members.length > 0;

  const avgMMR = useMemo(() => {
    if (!team.members || team.members.length === 0) return 0;
    const total = team.members.reduce(
      (sum: number, m: UserType) => sum + (m.mmr || 0),
      0
    );
    return Math.round(total / team.members.length);
  }, [team.members]);

  const totalMMR = useMemo(() => {
    if (!team.members || team.members.length === 0) return 0;
    return team.members.reduce(
      (sum: number, m: UserType) => sum + (m.mmr || 0),
      0
    );
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between">
            <span>{teamName}</span>
            {hasMembers && (
              <span className="text-sm font-normal text-muted-foreground">
                {team.members?.length} players | Avg: {avgMMR.toLocaleString()} MMR | Total: {totalMMR.toLocaleString()} MMR
              </span>
            )}
          </DialogTitle>
        </DialogHeader>

        {/* Captain Section */}
        <div className="flex items-center gap-4 p-3 bg-muted/50 rounded-lg">
          <img
            src={AvatarUrl(captain)}
            alt={`${captain.nickname || captain.username}'s avatar`}
            className="w-12 h-12 rounded-full border-2 border-primary"
          />
          <div className="flex-1">
            <div className="font-semibold">
              {captain.nickname || captain.username}
              <span className="ml-2 text-xs text-primary">(Captain)</span>
            </div>
            <div className="text-sm text-muted-foreground">
              {captain.mmr?.toLocaleString() || 'N/A'} MMR
            </div>
          </div>
          <RolePositions user={captain} />
        </div>

        {/* Team Members Table */}
        {hasMembers ? (
          <div className="max-h-[400px] overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[50px]">#</TableHead>
                  <TableHead>Player</TableHead>
                  <TableHead className="text-right">MMR</TableHead>
                  <TableHead>Positions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedMembers.map((member: UserType, idx: number) => (
                  <TableRow key={`team-modal-member-${member.pk}`}>
                    <TableCell className="font-medium text-muted-foreground">
                      {idx + 1}
                    </TableCell>
                    <TableCell>
                      <PlayerPopover player={member}>
                        <div className="flex items-center gap-3 cursor-pointer hover:text-primary transition-colors">
                          <img
                            src={AvatarUrl(member)}
                            alt={member.username}
                            className="w-8 h-8 rounded-full hover:ring-2 hover:ring-primary transition-all"
                          />
                          <span className="font-medium">
                            {member.nickname || member.username}
                          </span>
                          {member.pk === captain.pk && (
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
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <div className="p-8 text-center text-muted-foreground">
            No players drafted yet
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};
