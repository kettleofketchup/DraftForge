import { useMemo } from "react";
import { PlayerPopover } from "~/components/player";
import { cn } from "~/lib/utils";
import type { HeroDraft, HeroDraftTick } from "~/components/herodraft/types";
import type { UserType } from "~/components/user/types.d";
import { AvatarUrl, DisplayName } from "~/components/user/avatar";

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
 * Convert draft captain data to UserType for PlayerPopover/AvatarUrl compatibility
 */
function captainToUser(captain: {
  pk: number;
  username: string;
  nickname: string | null;
  avatar: string | null;
  avatarUrl?: string | null;
  discordId?: string | null;
}): UserType {
  return {
    pk: captain.pk,
    username: captain.username,
    nickname: captain.nickname,
    avatar: captain.avatar,
    avatarUrl: captain.avatarUrl ?? undefined,
    discordId: captain.discordId ?? undefined,
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

  // Get non-captain members (filter out captain from members list)
  const teamAMembers = useMemo(() => {
    if (!teamA?.members) return [];
    return teamA.members.filter((m) => m.pk !== teamA.captain?.pk).slice(0, 4);
  }, [teamA?.members, teamA?.captain?.pk]);

  const teamBMembers = useMemo(() => {
    if (!teamB?.members) return [];
    return teamB.members.filter((m) => m.pk !== teamB.captain?.pk).slice(0, 4);
  }, [teamB?.members, teamB?.captain?.pk]);

  // Helper to render a player avatar with name underneath
  const renderPlayer = (
    player: { pk: number; username: string; nickname: string | null; avatar: string | null; avatarUrl?: string | null; discordId?: string | null },
    isCaptain: boolean,
    testIdPrefix: string
  ) => (
    <PlayerPopover key={`player-${player.pk}`} player={captainToUser(player)}>
      <button
        className="flex flex-col items-center hover:bg-white/10 rounded p-1 min-w-[48px]"
        data-testid={`${testIdPrefix}-button`}
      >
        <img
          src={AvatarUrl(captainToUser(player))}
          alt={player.username}
          className={cn(
            "rounded-full",
            isCaptain ? "w-10 h-10 ring-2 ring-yellow-500" : "w-8 h-8 opacity-80 hover:opacity-100"
          )}
          data-testid={`${testIdPrefix}-avatar`}
        />
        <span
          className={cn(
            "text-xs truncate max-w-[56px] mt-1",
            isCaptain ? "font-semibold text-yellow-400" : "text-muted-foreground"
          )}
          data-testid={`${testIdPrefix}-name`}
        >
          {DisplayName(captainToUser(player))}
        </span>
      </button>
    </PlayerPopover>
  );

  return (
    <div className="bg-black/90 border-b border-gray-800" data-testid="herodraft-topbar">
      {/* Row 1: Teams - Captain on outer edges, members flowing inward */}
      <div className="flex items-center justify-between p-2" data-testid="herodraft-teams-row">
        {/* Team A: Captain on left, members flowing right */}
        <div className="flex items-center gap-1" data-testid="herodraft-team-a">
          {/* Captain - outer edge */}
          {teamA?.captain && renderPlayer(teamA.captain, true, "herodraft-team-a-captain")}
          {/* Team members */}
          {teamAMembers.map((member, idx) => renderPlayer(member, false, `herodraft-team-a-member-${idx}`))}
          {activeTeamId === teamA?.id && (
            <span className="text-yellow-400 text-sm animate-pulse ml-2" data-testid="herodraft-team-a-picking">
              ◀ PICKING
            </span>
          )}
        </div>

        {/* Center: VS and progress (only show progress during drafting) */}
        <div className="flex items-center gap-4">
          {draft.state === "drafting" || draft.state === "completed" ? (
            <>
              <div className="text-center text-xs text-muted-foreground" data-testid="herodraft-team-a-progress">
                {teamAProgress.completed}/{teamAProgress.total}
              </div>
              <div className="text-center" data-testid="herodraft-vs-section">
                <span className="text-2xl font-bold text-muted-foreground">VS</span>
              </div>
              <div className="text-center text-xs text-muted-foreground" data-testid="herodraft-team-b-progress">
                {teamBProgress.completed}/{teamBProgress.total}
              </div>
            </>
          ) : (
            <div className="text-center" data-testid="herodraft-vs-section">
              <span className="text-2xl font-bold text-muted-foreground">VS</span>
            </div>
          )}
        </div>

        {/* Team B: Members flowing left, Captain on right */}
        <div className="flex items-center gap-1" data-testid="herodraft-team-b">
          {activeTeamId === teamB?.id && (
            <span className="text-yellow-400 text-sm animate-pulse mr-2" data-testid="herodraft-team-b-picking">
              PICKING ▶
            </span>
          )}
          {/* Team members (reversed order so they flow toward center) */}
          {[...teamBMembers].reverse().map((member, idx) => renderPlayer(member, false, `herodraft-team-b-member-${idx}`))}
          {/* Captain - outer edge */}
          {teamB?.captain && renderPlayer(teamB.captain, true, "herodraft-team-b-captain")}
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
