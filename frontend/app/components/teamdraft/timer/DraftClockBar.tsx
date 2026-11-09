import { Pause } from 'lucide-react';
import { PrimaryButton, SecondaryButton, brandBg } from '~/components/ui/buttons';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import type { UserType } from '~/index';
import { cn } from '~/lib/utils';
import type { TeamDraftState } from '../schemas';
import { formatClock } from './formatClock';
import type { TeamDraftCountdown } from './useTeamDraftCountdown';

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
  onPause: () => Promise<unknown>;
  onStartClock: () => Promise<unknown>;
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

  const reservePct = (teamPk: number): number =>
    reserveTotalMs > 0 && armed
      ? Math.min(100, Math.round((100 * (armed.reserveByTeamId[teamPk] ?? 0)) / reserveTotalMs))
      : 0;

  const renderReserve = (team: ClockTeam, isActive: boolean) => {
    const testId = `draft-clock-reserve-${team.teamPk}`;
    if (!team.captain) {
      return (
        <span key={team.teamPk} data-testid={testId} data-empty="true" className="text-xs text-muted-foreground">
          —
        </span>
      );
    }
    if (!armed) return null;
    const ms = armed.reserveByTeamId[team.teamPk] ?? 0;
    const pct = reservePct(team.teamPk);
    if (isActive) {
      return (
        <div key={team.teamPk} data-testid={testId} data-pct={pct} className="flex items-center gap-2 min-w-[7rem]">
          <div className="h-2 flex-1 rounded bg-black/30 overflow-hidden">
            <div
              className={cn('h-full rounded bg-green-400', ms > 0 && pct < 20 && 'animate-reserve-critical')}
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="text-xs font-mono tabular-nums">{formatClock(ms)}</span>
        </div>
      );
    }
    return (
      <span
        key={team.teamPk}
        data-testid={testId}
        data-pct={pct}
        className="rounded bg-black/30 px-2 py-0.5 text-xs font-mono tabular-nums"
      >
        {formatClock(ms)}
      </span>
    );
  };

  return (
    <div
      data-testid="draft-clock-bar"
      className={cn('flex flex-wrap items-center justify-between gap-3 rounded-lg px-4 py-2 text-white', brandBg)}
    >
      <div className="flex items-center gap-2">
        {activeCaptain && (
          <div data-testid="draft-clock-active-captain" className="flex items-center gap-2">
            <UserAvatar user={activeCaptain} size="sm" border="captain" />
            <span className="font-semibold">{DisplayName(activeCaptain)}</span>
          </div>
        )}
        {isMyTurn && (
          <span data-testid="draft-clock-your-turn" className="rounded bg-green-500 px-2 py-0.5 text-xs font-bold">
            YOUR TURN
          </span>
        )}
      </div>

      <div className="flex items-center gap-3">
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
          <span
            data-testid="draft-clock-grace"
            className={cn(
              'text-2xl font-mono font-bold tabular-nums',
              armed && armed.graceRemainingMs < GRACE_URGENT_MS && 'animate-grace-urgent text-red-400',
            )}
          >
            {armed ? formatClock(armed.graceRemainingMs) : '—'}
          </span>
        )}
        {clockArmed && drafting && canControl && (
          <SecondaryButton data-testid="draft-clock-pause-button" onClick={() => void onPause()}>
            <Pause className="h-4 w-4 mr-2" />
            Pause
          </SecondaryButton>
        )}
      </div>

      <div className="flex items-center gap-2">
        {teams.map((t) => renderReserve(t, t.teamPk === activeTeamPk))}
      </div>
    </div>
  );
}
