import { toast } from 'sonner';
import { initDraftRounds } from '~/components/api/api';
import type { InitDraftRoundsResponse } from '~/components/api/draftAPI';
import type {
  DraftReferenceCounts,
  DraftResetConflict,
  DraftResetReport,
  DraftTeamUsage,
  InitDraftRoundsAPI,
} from '~/components/api/types';
import type { DraftRoundType, DraftType, TournamentType } from '~/index';
import { hydrateTournament } from '~/lib/hydrateTournament';
import { getLogger } from '~/lib/logger';
import {
  muteDraftStartToasts,
  useDraftWebSocketStore,
} from '~/store/draftWebSocketStore';
const log = getLogger('InitDraft');

export const DRAFT_RESET_HAS_REFERENCES = 'draft_reset_has_references';

export type ConfirmForceReset = (
  conflict: DraftResetConflict,
) => Promise<boolean>;

type hookParams = {
  tournament: TournamentType;
  setTournament: (tournament: TournamentType) => void;
  setDraft: (draft: DraftType) => void;
  curDraftRound: DraftRoundType;
  setCurDraftRound: (draftRound: DraftRoundType) => void;
  draftStyle?: 'snake' | 'normal' | 'shuffle';
  confirmForce: ConfirmForceReset;
  /** Called when the reset dropped or kept teams, so they can be named. */
  onReport?: (report: DraftResetReport) => void;
};

type InitDraftError = {
  message?: string;
  response?: {
    status?: number;
    data?: {
      error?: string;
      code?: string;
      references?: DraftReferenceCounts;
      usage?: DraftTeamUsage[];
    };
  };
};

const plural = (count: number, word: string) =>
  `${count} ${word}${count === 1 ? '' : 's'}`;

export const draftResetSummary = (report: DraftResetReport | undefined) => {
  if (!report) return 'Draft initialized.';
  const parts: string[] = [];
  if (report.reset_teams.length) {
    parts.push(
      `${plural(report.reset_teams.length, 'team')} reset to captains`,
    );
  }
  if (report.dropped_teams.length) {
    parts.push(`${report.dropped_teams.length} dropped`);
  }
  if (report.kept_teams.length) {
    parts.push(`${report.kept_teams.length} kept out of the draft`);
  }
  return parts.length
    ? `Draft initialized. ${parts.join(', ')}.`
    : 'Draft initialized.';
};

export const hasNamedOutcomes = (report: DraftResetReport | undefined) =>
  !!report && report.dropped_teams.length + report.kept_teams.length > 0;

const START_TOAST_MUTE_MS = 5000;

const conflictOf = (err: unknown): DraftResetConflict | null => {
  const response = (err as InitDraftError)?.response;
  if (response?.status !== 409) return null;
  if (response.data?.code !== DRAFT_RESET_HAS_REFERENCES) return null;
  return {
    references: response.data.references ?? {},
    usage: response.data.usage ?? [],
  };
};

const errorText = (err: unknown) => {
  const e = err as InitDraftError;
  return e?.response?.data?.error ?? e?.response?.data ?? e?.message;
};

/**
 * POST init-draft; on a references 409 ask `confirmForce` and re-POST with
 * `force: true`. Resolves with the tournament, or undefined when the draft
 * was not initialized (declined or failed; failures are toasted here).
 */
export const initDraftHook = async ({
  tournament,
  setTournament,
  setDraft,
  setCurDraftRound,
  draftStyle,
  confirmForce,
  onReport,
}: hookParams): Promise<TournamentType | undefined> => {
  log.debug('Initialization draft', { tournament });

  if (!tournament) {
    log.error('Creating tournamentNo tournament found');
    return;
  }

  if (!tournament.pk) {
    log.error('No tournament primary key found');
    return;
  }

  const data: InitDraftRoundsAPI = {
    tournament_pk: tournament.pk,
    ...(draftStyle && { draft_style: draftStyle }),
  };

  let toastId = toast.loading('Initializing draft rounds...');
  let rawData: InitDraftRoundsResponse;
  try {
    try {
      muteDraftStartToasts(START_TOAST_MUTE_MS);
      rawData = await initDraftRounds(data);
    } catch (err) {
      const conflict = conflictOf(err);
      if (!conflict) throw err;
      toast.dismiss(toastId);
      log.info('Draft reset needs force confirmation', {
        usage: conflict.usage.map((u) => `${u.model}:${u.count}`),
      });
      if (!(await confirmForce(conflict))) {
        log.info('Draft reset force declined');
        return;
      }
      toastId = toast.loading('Initializing draft rounds...');
      muteDraftStartToasts(START_TOAST_MUTE_MS);
      rawData = await initDraftRounds({ ...data, force: true });
    }
  } catch (err) {
    log.error('Tournament Draft has failed to Reinitialize!', err);
    toast.error(`Failed to initialize draft: ${errorText(err)}`, {
      id: toastId,
    });
    return;
  }

  log.debug('Draft init success, data:', rawData);
  const hydrated = hydrateTournament(
    rawData as TournamentType & { _users?: Record<number, unknown> },
  ) as TournamentType;
  setTournament(hydrated);
  if (hydrated.draft) {
    useDraftWebSocketStore.getState().dropStaleDraftState(hydrated.draft);
    setDraft(hydrated.draft);
    if (hydrated.draft.draft_rounds?.[0]) {
      setCurDraftRound(hydrated.draft.draft_rounds[0]);
    }
  } else {
    log.error('No draft in response');
  }
  toast.success(draftResetSummary(rawData.draft_reset), { id: toastId });
  if (rawData.draft_reset && hasNamedOutcomes(rawData.draft_reset)) {
    onReport?.(rawData.draft_reset);
  }
  return hydrated;
};
