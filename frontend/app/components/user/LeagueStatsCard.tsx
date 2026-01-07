import { cn } from "~/lib/utils";

interface LeagueStatsCardProps {
  stats: {
    games_played: number;
    win_rate: number;
    avg_kills: number;
    avg_deaths: number;
    avg_assists: number;
    avg_gpm: number;
    avg_xpm: number;
    mmr_adjustment: number;
  };
  baseMmr: number | null;
  leagueMmr: number | null;
  compact?: boolean;
}

export function LeagueStatsCard({
  stats,
  baseMmr,
  leagueMmr,
  compact = false,
}: LeagueStatsCardProps) {
  const adjustment = stats.mmr_adjustment;
  const adjustmentColor =
    adjustment > 0
      ? "text-green-500"
      : adjustment < 0
        ? "text-red-500"
        : "text-gray-500";
  const adjustmentText =
    adjustment > 0 ? `+${adjustment}` : String(adjustment);

  const winRatePercent = Math.round(stats.win_rate * 100);
  const winRateColor =
    winRatePercent >= 55
      ? "text-green-500"
      : winRatePercent <= 45
        ? "text-red-500"
        : "text-gray-300";

  if (compact) {
    return (
      <div className="space-y-1 text-sm">
        <div className="flex items-baseline gap-2">
          <span className="text-lg font-bold">
            {leagueMmr ?? baseMmr ?? "—"}
          </span>
          <span className={cn("text-xs", adjustmentColor)}>
            ({adjustmentText})
          </span>
        </div>
        <div className="text-gray-400">
          {stats.games_played} games •{" "}
          <span className={winRateColor}>{winRatePercent}% WR</span>
        </div>
        <div className="text-gray-400">
          KDA: {stats.avg_kills.toFixed(1)} / {stats.avg_deaths.toFixed(1)} /{" "}
          {stats.avg_assists.toFixed(1)}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 rounded-lg border border-gray-700 bg-gray-800 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-200">
          League Performance
        </h3>
        <div className="text-right">
          <div className="text-2xl font-bold text-white">
            {leagueMmr ?? baseMmr ?? "—"}
          </div>
          <div className={cn("text-sm", adjustmentColor)}>
            {adjustmentText} from base
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 text-center">
        <div>
          <div className="text-2xl font-bold text-white">
            {stats.games_played}
          </div>
          <div className="text-xs text-gray-400">Games</div>
        </div>
        <div>
          <div className={cn("text-2xl font-bold", winRateColor)}>
            {winRatePercent}%
          </div>
          <div className="text-xs text-gray-400">Win Rate</div>
        </div>
        <div>
          <div className="text-2xl font-bold text-white">
            {(
              (stats.avg_kills + stats.avg_assists) /
              Math.max(stats.avg_deaths, 1)
            ).toFixed(2)}
          </div>
          <div className="text-xs text-gray-400">KDA</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 border-t border-gray-700 pt-4">
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Avg Kills</span>
            <span className="text-white">{stats.avg_kills.toFixed(1)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Avg Deaths</span>
            <span className="text-white">{stats.avg_deaths.toFixed(1)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Avg Assists</span>
            <span className="text-white">{stats.avg_assists.toFixed(1)}</span>
          </div>
        </div>
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Avg GPM</span>
            <span className="text-white">{Math.round(stats.avg_gpm)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Avg XPM</span>
            <span className="text-white">{Math.round(stats.avg_xpm)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
