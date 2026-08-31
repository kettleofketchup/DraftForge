import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "~/components/ui/hover-card";
import { useUserLeagueStats } from "~/features/leaderboard/queries";
import { DisplayName } from "~/components/user/avatar";
import { LeagueStatsCard } from "./LeagueStatsCard";
import { UserAvatar } from "./UserAvatar";

interface UserPopoverProps {
  userId: number;
  username: string;
  nickname?: string | null;
  avatar?: string | null;
  /** Discord ID for proper avatar URL construction */
  discordId?: string | null;
  children?: React.ReactNode;
}

export function UserPopover({
  userId,
  username,
  nickname,
  avatar,
  discordId,
  children,
}: UserPopoverProps) {
  const { data: stats, isLoading } = useUserLeagueStats(userId);
  const displayName = DisplayName({ nickname, username });

  return (
    <HoverCard>
      <HoverCardTrigger asChild>
        {children ?? (
          <button className="cursor-pointer hover:underline">{displayName}</button>
        )}
      </HoverCardTrigger>
      <HoverCardContent className="w-64 border-gray-700 bg-gray-800">
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <UserAvatar
              user={{ nickname, username, avatar, discordId }}
              size="lg"
            />
            <div className="font-semibold text-white">{displayName}</div>
          </div>
          {isLoading ? (
            <div className="text-sm text-gray-400">Loading stats...</div>
          ) : stats ? (
            <LeagueStatsCard
              stats={stats}
              baseMmr={stats.base_mmr}
              leagueMmr={stats.league_mmr}
              compact
            />
          ) : (
            <div className="text-sm text-gray-400">No league stats</div>
          )}
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}
