import { Pause } from 'lucide-react';
import { PrimaryButton, SecondaryButton, brandBg } from '~/components/ui/buttons';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import type { UserType } from '~/index';
import { cn } from '~/lib/utils';
import type { TeamDraftState } from '../schemas';
import { formatDuration } from '~/lib/dota/utils';
import { useLiveTeamDraftCountdown, type TeamDraftCountdown } from './useTeamDraftCountdown';

const GRACE_URGENT_MS = 10_000;

export interface ClockTeam {
  teamPk: number;
  teamName: string | null;
  captain: UserType | null;
  isConnected: boolean;
}

export interface DraftClockBarProps {
  countdown: TeamDraftCountdown;
  timerEnabled: boolean;
  clockArmed: boolean;
  draftStatus: TeamDraftState | null;
  activeTeamPk: number | null;
  teams: ClockTeam[];
  isMyTurn: boolean;
  canControl: boolean;
  isStaff: boolean;
  reserveTotalMs: number;
  /** Never rejects: failures are toasted by runTimerAction. */
  onPause: () => Promise<void>;
  onStartClock: () => Promise<void>;
}

export type LiveDraftClockBarProps = Omit<DraftClockBarProps, 'countdown'>;

export function LiveDraftClockBar(props: LiveDraftClockBarProps) {
  const countdown = useLiveTeamDraftCountdown();
  return <DraftClockBar {...props} countdown={countdown} />;
}

export function DraftClockBar({
  countdown,
  timerEnabled,
  clockArmed,
  draftStatus,
  activeTeamPk,
  teams,
  isMyTurn,
  canControl,
  isStaff,
  reserveTotalMs,
  onPause,
  onStartClock,
}: DraftClockBarProps) {
  if (!timerEnabled) return null;

  const armed = countdown.kind === 'armed' ? countdown : null;
  const drafting = draftStatus === 'drafting';
  const activeTeam = teams.find((t) => t.teamPk === activeTeamPk) ?? null;
  const activeCaptain = activeTeam?.captain ?? null;
  const showUnarmed = !clockArmed && drafting;

  const activeReserveMs = armed && activeTeamPk != null ? (armed.reserveByTeamId[activeTeamPk] ?? 0) : 0;
  const inReserve = !!armed && !armed.expired && armed.graceRemainingMs <= 0;
  const reserveDraining = inReserve && drafting && activeReserveMs > 0;

  const reservePct = (teamPk: number): number =>
    reserveTotalMs > 0 && armed
      ? Math.min(100, Math.round((100 * (armed.reserveByTeamId[teamPk] ?? 0)) / reserveTotalMs))
      : 0;

  const renderReserve = (team: ClockTeam, isActive: boolean) => {
    const testId = `draft-clock-reserve-${team.teamPk}`;
    const label = team.captain ? DisplayName(team.captain) : (team.teamName ?? 'No captain');
    if (!team.captain) {
      return (
        <div key={team.teamPk} className="flex items-center gap-2 rounded-md bg-black/20 px-3 py-1.5 opacity-60">
          <span className="truncate text-xs">{label}</span>
          <span data-testid={testId} data-empty="true" className="text-xs text-muted-foreground">
            —
          </span>
        </div>
      );
    }
    if (!armed) return null;
    const ms = armed.reserveByTeamId[team.teamPk] ?? 0;
    const pct = reservePct(team.teamPk);
    const draining = isActive && reserveDraining;
    return (
      <div
        key={team.teamPk}
        data-active={isActive}
        className={cn(
          'flex min-w-[9rem] flex-col gap-1 rounded-md px-3 py-1.5',
          isActive ? 'bg-black/40 ring-1 ring-white/40' : 'bg-black/20 opacity-70',
          draining && 'ring-red-400',
        )}
      >
        <div className="flex items-center justify-between gap-3">
          <span className={cn('truncate text-xs', isActive && 'font-semibold')}>{label}</span>
          <span
            data-testid={testId}
            data-pct={pct}
            className={cn('font-mono text-sm tabular-nums', ms <= 0 && 'text-muted-foreground', draining && 'text-red-300')}
          >
            {formatDuration(ms / 1000)}
          </span>
        </div>
        <div className="h-1 rounded bg-black/40 overflow-hidden">
          <div
            className={cn('h-full rounded', draining ? 'bg-red-400' : 'bg-green-400')}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
    );
  };

  const clockLabel = 'text-[10px] font-semibold uppercase tracking-widest';
  const clockDigits = 'text-3xl md:text-4xl font-mono font-bold tabular-nums leading-none';
  const activePct = activeTeamPk != null ? reservePct(activeTeamPk) : 0;

  return (
    <>
      {reserveDraining && (
        <div
          data-testid="draft-reserve-tint"
          aria-hidden
          className="pointer-events-none fixed inset-0 z-40 bg-red-600/15 shadow-[inset_0_0_120px_rgba(239,68,68,0.45)]"
        />
      )}
      <div
        data-testid="draft-clock-bar"
        data-phase={armed?.expired ? 'expired' : inReserve ? 'reserve' : armed ? 'grace' : 'none'}
        className={cn(
          'flex flex-col gap-2 rounded-lg px-4 py-3 text-white',
          brandBg,
          reserveDraining && 'ring-2 ring-red-500',
        )}
      >
        <div className="grid grid-cols-1 items-center gap-3 md:grid-cols-[1fr_auto_1fr]">
          <div className="flex items-center gap-2 min-w-0">
            {activeCaptain && (
              <div data-testid="draft-clock-active-captain" className="flex items-center gap-2 min-w-0">
                <UserAvatar user={activeCaptain} size="sm" border="captain" />
                <span className="truncate font-semibold">{DisplayName(activeCaptain)}</span>
              </div>
            )}
            {isMyTurn && (
              <span data-testid="draft-clock-your-turn" className="rounded bg-green-500 px-2 py-0.5 text-xs font-bold">
                YOUR TURN
              </span>
            )}
          </div>

          <div className="flex items-center justify-center gap-3">
            {showUnarmed ? (
              <>
                <span data-testid="draft-clock-unarmed" className="rounded bg-black/30 px-2 py-0.5 text-sm">
                  No pick clock
                </span>
                {isStaff && (
                  <PrimaryButton data-testid="draft-clock-start-button" onClick={() => void onStartClock()}>
                    Start clock
                  </PrimaryButton>
                )}
              </>
            ) : armed?.expired ? (
              <span data-testid="draft-clock-expired" className="text-sm font-semibold text-red-300">
                Clock expired — waiting for {activeCaptain ? DisplayName(activeCaptain) : 'captain'} or staff to pick
              </span>
            ) : (
              <div className="flex items-stretch rounded-lg bg-black/30">
                <div className={cn('flex flex-col items-center gap-1 px-4 py-2', inReserve && 'opacity-40')}>
                  <span className={clockLabel}>Grace</span>
                  <span
                    data-testid="draft-clock-grace"
                    className={cn(
                      clockDigits,
                      armed && !inReserve && armed.graceRemainingMs < GRACE_URGENT_MS && 'animate-grace-urgent text-red-400',
                    )}
                  >
                    {armed ? formatDuration(armed.graceRemainingMs / 1000) : '—'}
                  </span>
                </div>
                <div className="w-px bg-white/20" />
                <div
                  className={cn(
                    'flex min-w-[7rem] flex-col items-center gap-1 rounded-r-lg px-4 py-2',
                    !inReserve && 'opacity-40',
                    reserveDraining && 'bg-red-600/30',
                  )}
                >
                  <span className={cn(clockLabel, reserveDraining && 'text-red-200')}>Reserve</span>
                  <span
                    data-testid="draft-clock-active-reserve"
                    className={cn(
                      clockDigits,
                      reserveDraining && 'text-red-300',
                      reserveDraining && activePct < 20 && 'animate-reserve-critical',
                    )}
                  >
                    {armed ? formatDuration(activeReserveMs / 1000) : '—'}
                  </span>
                  <div className="h-1 w-full rounded bg-black/40 overflow-hidden">
                    <div
                      className={cn('h-full rounded', reserveDraining ? 'bg-red-400' : 'bg-green-400')}
                      style={{ width: `${activePct}%` }}
                    />
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="flex items-center justify-end">
            {clockArmed && drafting && canControl && (
              <SecondaryButton data-testid="draft-clock-pause-button" onClick={() => void onPause()}>
                <Pause className="h-4 w-4 mr-2" />
                Pause
              </SecondaryButton>
            )}
          </div>
        </div>

        {armed && (
          <div className="flex flex-wrap items-center justify-center gap-2">
            {teams.map((t) => renderReserve(t, t.teamPk === activeTeamPk))}
          </div>
        )}
      </div>
    </>
  );
}
