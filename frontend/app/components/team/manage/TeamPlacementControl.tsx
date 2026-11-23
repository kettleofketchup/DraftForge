import { isAxiosError } from 'axios';
import { useState } from 'react';

import { ordinal, teamStatus } from '~/components/team/teamStatus';
import { Alert, AlertDescription } from '~/components/ui/alert';
import { PrimaryButton, SecondaryButton } from '~/components/ui/buttons';
import { Input } from '~/components/ui/input';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import { Textarea } from '~/components/ui/textarea';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { teamActionSchema } from './teamActionSchema';
import { useSetTeamPlacement } from './useTeamManagement';

const log = getLogger('teamManage');

const GENERIC_FAILURE = 'Something went wrong. Try again.';

export interface TeamPlacementControlProps {
  tournamentId: number;
  teamId: number;
  teamName: string;
  placement: number | null | undefined;
}

/** A whole number of at least 1, or null for anything else. */
export function parsePlacement(value: string): number | null {
  const trimmed = value.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const n = Number(trimmed);
  return n >= 1 ? n : null;
}

/** What saving `next` does to the team, named for the confirmation step. */
export function placementEffect(
  teamName: string,
  current: number | null | undefined,
  next: number | null,
): { question: string; confirmText: string } {
  if (next == null) {
    return {
      question: `Put ${teamName} back in the tournament? Its players count as on this team again and cannot join other teams.`,
      confirmText: 'Put back in tournament',
    };
  }
  if (current != null) {
    return {
      question: `Change ${teamName}'s placement from ${ordinal(current)} to ${ordinal(next)}?`,
      confirmText: 'Change placement',
    };
  }
  const label = teamStatus(next) === 'winner' ? 'the winner' : 'eliminated';
  return {
    question: `Mark ${teamName} ${label} (${ordinal(next)})? It leaves the tournament and its players become free to join other teams.`,
    confirmText: 'Set placement',
  };
}

const errorCode = (err: unknown): string | undefined => {
  if (!isAxiosError(err)) return undefined;
  const data: unknown = err.response?.data;
  return data && typeof data === 'object' && 'code' in data
    ? String(data.code)
    : undefined;
};

export function TeamPlacementControl({
  tournamentId,
  teamId,
  teamName,
  placement,
}: TeamPlacementControlProps) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState('');
  const [pending, setPending] = useState<{ next: number | null } | null>(null);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const mutation = useSetTeamPlacement(teamId, tournamentId);
  const parsed = parsePlacement(value);
  const reasonCheck = teamActionSchema.safeParse({ reason });

  const handleOpenChange = (next: boolean) => {
    if (next) setValue(placement == null ? '' : String(placement));
    setPending(null);
    setReason('');
    setError(null);
    setOpen(next);
  };

  const review = (next: number | null) => {
    setError(null);
    setPending({ next });
  };

  const submit = () => {
    if (!pending || !reasonCheck.success) return;
    setError(null);
    mutation.mutate(
      { placement: pending.next, reason: reasonCheck.data.reason },
      {
        onSuccess: () => setOpen(false),
        onError: (err) => {
          const status = isAxiosError(err) ? err.response?.status : undefined;
          setError(extractApiError(err) ?? GENERIC_FAILURE);
          log.warn('Team placement refused', {
            teamId,
            status,
            code: errorCode(err),
          });
        },
      },
    );
  };

  const effect = pending
    ? placementEffect(teamName, placement, pending.next)
    : null;

  const errorAlert = error ? (
    <Alert variant="destructive" data-testid="team-placement-error">
      <AlertDescription>{error}</AlertDescription>
    </Alert>
  ) : null;

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <SecondaryButton size="sm" data-testid="team-placement-trigger">
          Set placement
        </SecondaryButton>
      </PopoverTrigger>
      <PopoverContent align="start" className="flex w-80 flex-col gap-3">
        {effect ? (
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <p className="text-sm" data-testid="team-placement-confirm-text">
              {effect.question}
            </p>
            <label className="flex flex-col gap-1 text-sm">
              Reason (recorded in team history)
              <Textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={2}
                data-testid="team-placement-reason"
              />
            </label>
            {errorAlert}
            <div className="flex flex-wrap justify-end gap-2">
              <SecondaryButton
                type="button"
                size="sm"
                disabled={mutation.isPending}
                onClick={() => {
                  setError(null);
                  setPending(null);
                }}
                data-testid="team-placement-back"
              >
                Back
              </SecondaryButton>
              <PrimaryButton
                type="submit"
                size="sm"
                disabled={!reasonCheck.success || mutation.isPending}
                data-testid="team-placement-confirm"
              >
                {effect.confirmText}
              </PrimaryButton>
            </div>
          </form>
        ) : (
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (parsed != null) review(parsed);
            }}
          >
            <label className="flex flex-col gap-1 text-sm">
              Placement
              <Input
                type="number"
                inputMode="numeric"
                min={1}
                step={1}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                data-testid="team-placement-input"
              />
            </label>
            <div className="flex flex-wrap justify-end gap-2">
              <SecondaryButton
                type="button"
                size="sm"
                disabled={placement == null}
                onClick={() => review(null)}
                data-testid="team-placement-clear"
              >
                Clear (back in tournament)
              </SecondaryButton>
              <PrimaryButton
                type="submit"
                size="sm"
                disabled={parsed == null || parsed === placement}
                data-testid="team-placement-save"
              >
                Save
              </PrimaryButton>
            </div>
          </form>
        )}
      </PopoverContent>
    </Popover>
  );
}
