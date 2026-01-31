import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "~/components/ui/hover-card";
import { useUserLeagueStats } from "~/features/leaderboard/queries";
import { LeagueStatsCard } from "./LeagueStatsCard";
import { UserAvatar } from "./UserAvatar";

interface UserPopoverProps {
  userId: number;
  username: string;
  avatar?: string | null;
  /** Discord ID for proper avatar URL construction */
  discordId?: string | null;
  children?: React.ReactNode;
}

export function UserPopover({
  userId,
  username,
  avatar,
  discordId,
  children,
}: UserPopoverProps) {
  const { data: stats, isLoading } = useUserLeagueStats(userId);

  return (
    <HoverCard>
      <HoverCardTrigger asChild>
        {children ?? (
          <button className="cursor-pointer hover:underline">{username}</button>
        )}
      </HoverCardTrigger>
      <HoverCardContent className="w-64 border-gray-700 bg-gray-800">
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <UserAvatar
              user={{ username, avatar, discordId }}
              size="lg"
            />
            <div className="font-semibold text-white">{username}</div>
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
