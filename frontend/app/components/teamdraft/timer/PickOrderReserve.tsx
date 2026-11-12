import { formatDuration } from '~/lib/dota/utils';
import { cn } from '~/lib/utils';
import { draftWsSelectors, useDraftWebSocketStore } from '~/store/draftWebSocketStore';
import type { TeamDraftState } from '../schemas';
import { useLiveTeamDraftCountdown, type TeamDraftCountdown } from './useTeamDraftCountdown';

export interface PickOrderReserveProps {
  teamPk: number;
  isCurrent: boolean;
  countdown: TeamDraftCountdown;
  draftStatus: TeamDraftState | null;
  reserveTotalMs: number;
}

export function PickOrderReserve({ teamPk, isCurrent, countdown, draftStatus, reserveTotalMs }: PickOrderReserveProps) {
  if (countdown.kind !== 'armed') return null;
  const ms = countdown.reserveByTeamId[teamPk] ?? 0;
  const pct = reserveTotalMs > 0 ? Math.min(100, Math.round((100 * ms) / reserveTotalMs)) : 0;
  const draining =
    isCurrent && draftStatus === 'drafting' && !countdown.expired && countdown.graceRemainingMs <= 0 && ms > 0;
  return (
    <span
      data-testid={`draft-clock-reserve-${teamPk}`}
      data-pct={pct}
      data-draining={draining}
      title="Reserve time"
      className={cn(
        'rounded px-1.5 py-0.5 font-mono text-[10px] md:text-xs tabular-nums',
        draining
          ? 'bg-red-600/30 text-red-300 ring-1 ring-red-500'
          : ms <= 0
            ? 'bg-black/20 text-muted-foreground'
            : 'bg-black/30 text-green-300',
        draining && reserveTotalMs > 0 && pct < 20 && 'animate-reserve-critical',
      )}
    >
      {formatDuration(ms / 1000)}
    </span>
  );
}

interface LivePickOrderReserveProps {
  teamPk: number;
  isCurrent: boolean;
}

export function LivePickOrderReserve(props: LivePickOrderReserveProps) {
  const timerEnabled = useDraftWebSocketStore(draftWsSelectors.timerEnabled);
  return timerEnabled ? <TickingPickOrderReserve {...props} /> : null;
}

function TickingPickOrderReserve({ teamPk, isCurrent }: LivePickOrderReserveProps) {
  const draftStatus = useDraftWebSocketStore(draftWsSelectors.draftStatus);
  const reserveTotalMs = useDraftWebSocketStore((s) => s.draftState?.draft_options?.reserve_time_ms ?? 0);
  const countdown = useLiveTeamDraftCountdown();
  return (
    <PickOrderReserve
      teamPk={teamPk}
      isCurrent={isCurrent}
      countdown={countdown}
      draftStatus={draftStatus}
      reserveTotalMs={reserveTotalMs}
    />
  );
}
