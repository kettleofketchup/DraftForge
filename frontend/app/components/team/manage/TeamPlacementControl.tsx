import { isAxiosError } from 'axios';
import { useState } from 'react';

import { Alert, AlertDescription } from '~/components/ui/alert';
import { PrimaryButton, SecondaryButton } from '~/components/ui/buttons';
import { Input } from '~/components/ui/input';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { useSetTeamPlacement } from './useTeamManagement';

const log = getLogger('teamManage');

const GENERIC_FAILURE = 'Something went wrong. Try again.';

export interface TeamPlacementControlProps {
  tournamentId: number;
  teamId: number;
  placement: number | null | undefined;
}

/** A whole number of at least 1, or null for anything else. */
export function parsePlacement(value: string): number | null {
  const trimmed = value.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const n = Number(trimmed);
  return n >= 1 ? n : null;
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
  placement,
}: TeamPlacementControlProps) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const mutation = useSetTeamPlacement(teamId, tournamentId);
  const parsed = parsePlacement(value);

  const handleOpenChange = (next: boolean) => {
    if (next) setValue(placement == null ? '' : String(placement));
    setError(null);
    setOpen(next);
  };

  const submit = (next: number | null) => {
    setError(null);
    mutation.mutate(next, {
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
    });
  };

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <SecondaryButton size="sm" data-testid="team-placement-trigger">
          Set placement
        </SecondaryButton>
      </PopoverTrigger>
      <PopoverContent align="start" className="flex w-72 flex-col gap-3">
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (parsed != null) submit(parsed);
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
          {error ? (
            <Alert variant="destructive" data-testid="team-placement-error">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          <div className="flex flex-wrap justify-end gap-2">
            <SecondaryButton
              type="button"
              size="sm"
              disabled={placement == null || mutation.isPending}
              onClick={() => submit(null)}
              data-testid="team-placement-clear"
            >
              Clear (back in tournament)
            </SecondaryButton>
            <PrimaryButton
              type="submit"
              size="sm"
              disabled={parsed == null || mutation.isPending}
              data-testid="team-placement-save"
            >
              Save
            </PrimaryButton>
          </div>
        </form>
      </PopoverContent>
    </Popover>
  );
}
