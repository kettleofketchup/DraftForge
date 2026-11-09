import { elapsedSince, remaining, serverNow, useAnimationFrameClock } from '~/lib/draftClock';
import { useDraftWebSocketStore } from '~/store/draftWebSocketStore';
import type { DraftTick, TeamDraftState } from '../schemas';

export type TeamDraftCountdown =
  | { kind: 'unarmed' }
  | {
      kind: 'armed';
      graceRemainingMs: number;
      reserveByTeamId: Record<number, number>;
      resumingRemainingMs: number;
      expired: boolean;
    };

export interface CountdownDraftSlice {
  state: TeamDraftState | null | undefined;
  paused_at?: string | null;
  resuming_until?: string | null;
  clock_armed?: boolean;
  latest_round?: number | null;
  draft_rounds?: ReadonlyArray<{
    pk: number;
    started_at?: string | null;
    timed_out_at?: string | null;
    grace_time_ms?: number | null;
    captain?: { pk?: number } | null;
  }> | null;
  tournament?: {
    teams?: ReadonlyArray<{
      pk: number | null;
      draft_reserve_ms?: number | null;
      captain?: { pk?: number } | null;
    }> | null;
  } | null;
}

interface Source {
  anchor: string | null;
  grace: number | null;
  reserves: Array<[number, number]>;
  activeTeamId: number | null;
  expired: boolean;
  resumingTarget: string | null;
}

const UNARMED: TeamDraftCountdown = { kind: 'unarmed' };

function tickSource(tick: DraftTick): Source {
  return {
    anchor: tick.round_started_at,
    grace: tick.round_grace_time_ms,
    reserves: tick.teams.map((t) => [t.team_id, t.reserve_ms ?? 0]),
    activeTeamId: tick.active_team_id,
    expired: tick.round_timed_out_at !== null,
    resumingTarget: tick.draft_state === 'resuming' ? (tick.resuming_until ?? null) : null,
  };
}

function serializedSource(draft: CountdownDraftSlice): Source {
  const round = draft.draft_rounds?.find((r) => r.pk === draft.latest_round);
  const teams = draft.tournament?.teams ?? [];
  const captainPk = round?.captain?.pk;
  const active = captainPk == null ? undefined : teams.find((t) => t.captain?.pk === captainPk);
  const reserves: Array<[number, number]> = [];
  for (const t of teams) {
    if (t.pk != null) reserves.push([t.pk, t.draft_reserve_ms ?? 0]);
  }
  return {
    anchor: round?.started_at ?? null,
    grace: round?.grace_time_ms ?? null,
    reserves,
    activeTeamId: active?.pk ?? null,
    expired: round?.timed_out_at != null,
    resumingTarget: draft.state === 'resuming' ? (draft.resuming_until ?? null) : null,
  };
}

function compute(src: Source, nowMs: number): TeamDraftCountdown {
  if (!src.anchor || typeof src.grace !== 'number') return UNARMED;
  let at = nowMs;
  let resumingRemainingMs = 0;
  if (src.resumingTarget) {
    const target = Date.parse(src.resumingTarget);
    if (!Number.isNaN(target)) {
      at = target;
      resumingRemainingMs = Math.max(0, target - nowMs);
    }
  }
  const consumed = Math.max(0, elapsedSince(src.anchor, at) - src.grace);
  const reserveByTeamId: Record<number, number> = {};
  for (const [teamId, reserve] of src.reserves) {
    reserveByTeamId[teamId] = teamId === src.activeTeamId ? Math.max(0, reserve - consumed) : reserve;
  }
  return {
    kind: 'armed',
    graceRemainingMs: remaining(src.anchor, src.grace, at),
    reserveByTeamId,
    resumingRemainingMs,
    expired: src.expired,
  };
}

export function _deriveTeamCountdown(
  tick: DraftTick | null,
  draft: CountdownDraftSlice | null,
  serverClockOffsetMs: number,
  nowMs: number,
): TeamDraftCountdown {
  void serverClockOffsetMs;
  const matching = tick && (!draft || tick.active_round_pk === draft.latest_round) ? tick : null;

  if (draft?.state === 'paused') {
    const pausedAt = draft.paused_at ? Date.parse(draft.paused_at) : NaN;
    return compute(matching ? tickSource(matching) : serializedSource(draft), Number.isNaN(pausedAt) ? nowMs : pausedAt);
  }
  if (draft && draft.clock_armed !== true) return UNARMED;
  if (matching) return compute(tickSource(matching), nowMs);
  if (draft) return compute(serializedSource(draft), nowMs);
  return UNARMED;
}

export function useTeamDraftCountdown(
  tick: DraftTick | null,
  draft: CountdownDraftSlice | null,
  serverClockOffsetMs: number,
): TeamDraftCountdown {
  return useAnimationFrameClock({
    derive: () => _deriveTeamCountdown(tick, draft, serverClockOffsetMs, serverNow(serverClockOffsetMs)),
    isFrozen: draft?.state === 'paused',
    inputs: [tick, draft, serverClockOffsetMs],
  });
}

export function useLiveTeamDraftCountdown(): TeamDraftCountdown {
  const tick = useDraftWebSocketStore((s) => s.tick);
  const draftState = useDraftWebSocketStore((s) => s.draftState);
  const serverClockOffsetMs = useDraftWebSocketStore((s) => s.serverClockOffsetMs);
  return useTeamDraftCountdown(tick, draftState as CountdownDraftSlice | null, serverClockOffsetMs);
}
