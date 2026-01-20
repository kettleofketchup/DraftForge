import { useMemo } from "react";
import { PlayerPopover } from "~/components/player";
import { cn } from "~/lib/utils";
import type { HeroDraft, HeroDraftTick } from "~/components/herodraft/types";
import type { UserType } from "~/components/user/types.d";

interface DraftTopBarProps {
  draft: HeroDraft;
  tick: HeroDraftTick | null;
}

function formatTime(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

/**
 * Convert draft captain data to UserType for PlayerPopover compatibility
 */
function captainToUser(captain: {
  id: number;
  username: string;
  nickname: string | null;
  avatar: string | null;
}): UserType {
  return {
    pk: captain.id,
    username: captain.username,
    nickname: captain.nickname,
    avatar: captain.avatar,
  };
}

export function DraftTopBar({ draft, tick }: DraftTopBarProps) {
  // Safely access teams with bounds checking
  const teamA = draft.draft_teams?.[0] ?? null;
  const teamB = draft.draft_teams?.[1] ?? null;

  const activeTeamId = tick?.active_team_id;
  const graceRemaining = tick?.grace_time_remaining_ms ?? 0;

  // Match reserve times by team ID for correctness
  const getTeamReserve = (team: typeof teamA) => {
    if (!team || !tick) return team?.reserve_time_remaining ?? 90000;
    if (tick.team_a_id === team.id) return tick.team_a_reserve_ms;
    if (tick.team_b_id === team.id) return tick.team_b_reserve_ms;
    return team.reserve_time_remaining ?? 90000;
  };

  const teamAReserve = getTeamReserve(teamA);
  const teamBReserve = getTeamReserve(teamB);

  // Find current round from rounds array using current_round index
  const currentRoundIndex = draft.current_round;
  const currentRound =
    currentRoundIndex !== null ? draft.rounds[currentRoundIndex] : null;
  const currentAction = currentRound?.action_type ?? "pick";

  // Memoize progress counts to avoid filtering on every tick update
  const teamAProgress = useMemo(() => {
    const completed = draft.rounds.filter(
      (r) => r.draft_team === teamA?.id && r.state === "completed"
    ).length;
    const total = draft.rounds.filter((r) => r.draft_team === teamA?.id).length;
    return { completed, total };
  }, [draft.rounds, teamA?.id]);

  const teamBProgress = useMemo(() => {
    const completed = draft.rounds.filter(
      (r) => r.draft_team === teamB?.id && r.state === "completed"
    ).length;
    const total = draft.rounds.filter((r) => r.draft_team === teamB?.id).length;
    return { completed, total };
  }, [draft.rounds, teamB?.id]);

  return (
    <div className="bg-black/90 border-b border-gray-800" data-testid="herodraft-topbar">
      {/* Row 1: Captains */}
      <div className="grid grid-cols-5 items-center p-2" data-testid="herodraft-captains-row">
        {/* Team A Captain */}
        <div className="flex items-center gap-2" data-testid="herodraft-team-a-captain">
          {teamA?.captain && (
            <PlayerPopover player={captainToUser(teamA.captain)}>
              <button className="flex items-center gap-2 hover:bg-white/10 rounded p-1" data-testid="herodraft-team-a-captain-button">
                <img
                  src={teamA.captain.avatar || "/default-avatar.png"}
                  alt={teamA.captain.username}
                  className="w-10 h-10 rounded-full"
                  data-testid="herodraft-team-a-avatar"
                />
                <div className="text-left">
                  <p className="font-semibold text-sm" data-testid="herodraft-team-a-name">
                    {teamA.captain.nickname || teamA.captain.username}
                  </p>
                  <p className="text-xs text-muted-foreground" data-testid="herodraft-team-a-side">
                    {teamA.is_radiant ? "Radiant" : "Dire"}
                  </p>
                </div>
              </button>
            </PlayerPopover>
          )}
          {activeTeamId === teamA?.id && (
            <span className="text-yellow-400 text-sm animate-pulse" data-testid="herodraft-team-a-picking">
              ◀ PICKING
            </span>
          )}
        </div>

        {/* Team A Bans/Picks summary */}
        <div className="text-center text-xs text-muted-foreground" data-testid="herodraft-team-a-progress">
          {teamAProgress.completed} / {teamAProgress.total}
        </div>

        {/* VS / Current action */}
        <div className="text-center" data-testid="herodraft-vs-section">
          <span className="text-2xl font-bold text-muted-foreground">VS</span>
        </div>

        {/* Team B Bans/Picks summary */}
        <div className="text-center text-xs text-muted-foreground" data-testid="herodraft-team-b-progress">
          {teamBProgress.completed} / {teamBProgress.total}
        </div>

        {/* Team B Captain */}
        <div className="flex items-center gap-2 justify-end" data-testid="herodraft-team-b-captain">
          {activeTeamId === teamB?.id && (
            <span className="text-yellow-400 text-sm animate-pulse" data-testid="herodraft-team-b-picking">
              PICKING ▶
            </span>
          )}
          {teamB?.captain && (
            <PlayerPopover player={captainToUser(teamB.captain)}>
              <button className="flex items-center gap-2 hover:bg-white/10 rounded p-1" data-testid="herodraft-team-b-captain-button">
                <div className="text-right">
                  <p className="font-semibold text-sm" data-testid="herodraft-team-b-name">
                    {teamB.captain.nickname || teamB.captain.username}
                  </p>
                  <p className="text-xs text-muted-foreground" data-testid="herodraft-team-b-side">
                    {teamB.is_radiant ? "Radiant" : "Dire"}
                  </p>
                </div>
                <img
                  src={teamB.captain.avatar || "/default-avatar.png"}
                  alt={teamB.captain.username}
                  className="w-10 h-10 rounded-full"
                  data-testid="herodraft-team-b-avatar"
                />
              </button>
            </PlayerPopover>
          )}
        </div>
      </div>

      {/* Row 2: Timers */}
      <div className="grid grid-cols-5 items-center p-2 border-t border-gray-800" data-testid="herodraft-timers-row">
        {/* Team A Reserve */}
        <div
          className={cn(
            "text-center font-mono text-lg",
            teamAReserve < 30000 && "text-red-400"
          )}
          data-testid="herodraft-team-a-reserve"
        >
          <span className="text-xs text-muted-foreground block">Reserve</span>
          <span data-testid="herodraft-team-a-reserve-time">{formatTime(teamAReserve)}</span>
        </div>

        <div />

        {/* Current pick timer */}
        <div className="text-center" data-testid="herodraft-grace-timer">
          <span className="text-xs text-muted-foreground block uppercase" data-testid="herodraft-current-action">
            {currentAction} Time
          </span>
          <span
            className={cn(
              "font-mono text-2xl font-bold",
              graceRemaining < 10000 ? "text-red-400" : "text-yellow-400"
            )}
            data-testid="herodraft-grace-time"
          >
            {formatTime(graceRemaining)}
          </span>
        </div>

        <div />

        {/* Team B Reserve */}
        <div
          className={cn(
            "text-center font-mono text-lg",
            teamBReserve < 30000 && "text-red-400"
          )}
          data-testid="herodraft-team-b-reserve"
        >
          <span className="text-xs text-muted-foreground block">Reserve</span>
          <span data-testid="herodraft-team-b-reserve-time">{formatTime(teamBReserve)}</span>
        </div>
      </div>
    </div>
  );
}
