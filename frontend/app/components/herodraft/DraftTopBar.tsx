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
  const teamA = draft.draft_teams[0];
  const teamB = draft.draft_teams[1];

  const activeTeamId = tick?.active_team_id;
  const graceRemaining = tick?.grace_time_remaining_ms ?? 0;

  const teamAReserve =
    tick?.team_a_reserve_ms ?? teamA?.reserve_time_remaining ?? 90000;
  const teamBReserve =
    tick?.team_b_reserve_ms ?? teamB?.reserve_time_remaining ?? 90000;

  // Find current round from rounds array using current_round index
  const currentRoundIndex = draft.current_round;
  const currentRound =
    currentRoundIndex !== null ? draft.rounds[currentRoundIndex] : null;
  const currentAction = currentRound?.action_type ?? "pick";

  return (
    <div className="bg-black/90 border-b border-gray-800">
      {/* Row 1: Captains */}
      <div className="grid grid-cols-5 items-center p-2">
        {/* Team A Captain */}
        <div className="flex items-center gap-2">
          {teamA?.captain && (
            <PlayerPopover player={captainToUser(teamA.captain)}>
              <button className="flex items-center gap-2 hover:bg-white/10 rounded p-1">
                <img
                  src={teamA.captain.avatar || "/default-avatar.png"}
                  alt={teamA.captain.username}
                  className="w-10 h-10 rounded-full"
                />
                <div className="text-left">
                  <p className="font-semibold text-sm">
                    {teamA.captain.nickname || teamA.captain.username}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {teamA.is_radiant ? "Radiant" : "Dire"}
                  </p>
                </div>
              </button>
            </PlayerPopover>
          )}
          {activeTeamId === teamA?.id && (
            <span className="text-yellow-400 text-sm animate-pulse">
              ◀ PICKING
            </span>
          )}
        </div>

        {/* Team A Bans/Picks summary */}
        <div className="text-center text-xs text-muted-foreground">
          {
            draft.rounds.filter(
              (r) => r.draft_team === teamA?.id && r.state === "completed"
            ).length
          }{" "}
          / {draft.rounds.filter((r) => r.draft_team === teamA?.id).length}
        </div>

        {/* VS / Current action */}
        <div className="text-center">
          <span className="text-2xl font-bold text-muted-foreground">VS</span>
        </div>

        {/* Team B Bans/Picks summary */}
        <div className="text-center text-xs text-muted-foreground">
          {
            draft.rounds.filter(
              (r) => r.draft_team === teamB?.id && r.state === "completed"
            ).length
          }{" "}
          / {draft.rounds.filter((r) => r.draft_team === teamB?.id).length}
        </div>

        {/* Team B Captain */}
        <div className="flex items-center gap-2 justify-end">
          {activeTeamId === teamB?.id && (
            <span className="text-yellow-400 text-sm animate-pulse">
              PICKING ▶
            </span>
          )}
          {teamB?.captain && (
            <PlayerPopover player={captainToUser(teamB.captain)}>
              <button className="flex items-center gap-2 hover:bg-white/10 rounded p-1">
                <div className="text-right">
                  <p className="font-semibold text-sm">
                    {teamB.captain.nickname || teamB.captain.username}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {teamB.is_radiant ? "Radiant" : "Dire"}
                  </p>
                </div>
                <img
                  src={teamB.captain.avatar || "/default-avatar.png"}
                  alt={teamB.captain.username}
                  className="w-10 h-10 rounded-full"
                />
              </button>
            </PlayerPopover>
          )}
        </div>
      </div>

      {/* Row 2: Timers */}
      <div className="grid grid-cols-5 items-center p-2 border-t border-gray-800">
        {/* Team A Reserve */}
        <div
          className={cn(
            "text-center font-mono text-lg",
            teamAReserve < 30000 && "text-red-400"
          )}
        >
          <span className="text-xs text-muted-foreground block">Reserve</span>
          {formatTime(teamAReserve)}
        </div>

        <div />

        {/* Current pick timer */}
        <div className="text-center">
          <span className="text-xs text-muted-foreground block uppercase">
            {currentAction} Time
          </span>
          <span
            className={cn(
              "font-mono text-2xl font-bold",
              graceRemaining < 10000 ? "text-red-400" : "text-yellow-400"
            )}
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
        >
          <span className="text-xs text-muted-foreground block">Reserve</span>
          {formatTime(teamBReserve)}
        </div>
      </div>
    </div>
  );
}
