import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '~/components/ui/hover-card';
import { useUserLeagueStats } from '~/features/leaderboard/queries';
import { useDisplayName } from '~/hooks/useDisplayName';
import { useDisplayOrgId } from '~/hooks/useDisplayOrgId';
import { LeagueStatsCard } from './LeagueStatsCard';
import { UserAvatar } from './UserAvatar';

interface UserPopoverProps {
  userId: number;
  username: string;
  discordNickname?: string | null;
  avatar?: string | null;
  /** Discord ID for proper avatar URL construction */
  discordId?: string | null;
  children?: React.ReactNode;
}

export function UserPopover({
  userId,
  username,
  discordNickname,
  avatar,
  discordId,
  children,
}: UserPopoverProps) {
  const { data: stats, isLoading } = useUserLeagueStats(userId);
  const displayName = useDisplayName(
    { pk: userId, username, discordNickname },
    useDisplayOrgId(),
  );

  return (
    <HoverCard>
      <HoverCardTrigger asChild>
        {children ?? (
          <button className="cursor-pointer hover:underline">
            {displayName}
          </button>
        )}
      </HoverCardTrigger>
      <HoverCardContent className="w-64 border-border bg-base-800">
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <UserAvatar
              user={{ discordNickname, username, avatar, discordId }}
              size="lg"
            />
            <div className="font-semibold text-white">{displayName}</div>
          </div>
          {isLoading ? (
            <div className="text-sm text-muted-foreground">
              Loading stats...
            </div>
          ) : stats ? (
            <LeagueStatsCard
              stats={stats}
              baseMmr={stats.base_mmr}
              leagueMmr={stats.league_mmr}
              compact
            />
          ) : (
            <div className="text-sm text-muted-foreground">No league stats</div>
          )}
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}
