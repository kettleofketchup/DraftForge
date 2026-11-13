import {
  formatWinRate,
  toneClass,
  winRateTone,
} from "~/features/league-stats/format";
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
      ? "text-success"
      : adjustment < 0
        ? "text-destructive"
        : "text-muted-foreground";
  const adjustmentText =
    adjustment > 0 ? `+${adjustment}` : String(adjustment);

  const winRateText = formatWinRate(stats.win_rate);
  const winRateColor = toneClass[winRateTone(stats.win_rate)];

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
        <div className="text-muted-foreground">
          {stats.games_played} games •{" "}
          <span className={winRateColor}>{winRateText} WR</span>
        </div>
        <div className="text-muted-foreground">
          KDA: {stats.avg_kills.toFixed(1)} / {stats.avg_deaths.toFixed(1)} /{" "}
          {stats.avg_assists.toFixed(1)}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 rounded-lg border border-border bg-base-800 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-foreground">
          League Performance
        </h3>
        <div className="text-right">
          <div className="text-2xl font-bold text-foreground">
            {leagueMmr ?? baseMmr ?? "—"}
          </div>
          <div className={cn("text-sm", adjustmentColor)}>
            {adjustmentText} from base
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 text-center">
        <div>
          <div className="text-2xl font-bold text-foreground">
            {stats.games_played}
          </div>
          <div className="text-xs text-muted-foreground">Games</div>
        </div>
        <div>
          <div
            className={cn("text-2xl font-bold text-foreground", winRateColor)}
          >
            {winRateText}
          </div>
          <div className="text-xs text-muted-foreground">Win Rate</div>
        </div>
        <div>
          <div className="text-2xl font-bold text-foreground">
            {(
              (stats.avg_kills + stats.avg_assists) /
              Math.max(stats.avg_deaths, 1)
            ).toFixed(2)}
          </div>
          <div className="text-xs text-muted-foreground">KDA</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 border-t border-border pt-4">
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Avg Kills</span>
            <span className="text-foreground">{stats.avg_kills.toFixed(1)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Avg Deaths</span>
            <span className="text-foreground">{stats.avg_deaths.toFixed(1)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Avg Assists</span>
            <span className="text-foreground">{stats.avg_assists.toFixed(1)}</span>
          </div>
        </div>
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Avg GPM</span>
            <span className="text-foreground">{Math.round(stats.avg_gpm)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Avg XPM</span>
            <span className="text-foreground">{Math.round(stats.avg_xpm)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
