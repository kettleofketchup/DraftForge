import { fetchDraft } from '~/components/api/api';
import type { DraftType } from '~/index';
import { hydrateDraft } from '~/lib/hydrateTournament';
import { getLogger } from '~/lib/logger';
const log = getLogger('RefreshDraftHook');

type hookParams = {
  draft: DraftType;
  setDraft: (draft: DraftType) => void;
};

export const refreshDraftHook = async ({ draft, setDraft }: hookParams) => {
  if (!draft) {
    log.error('No draft found');
    return;
  }

  if (!draft.pk) {
    log.error('No tournament primary key found');
    return;
  }
  log.debug('refreshing draft', draft.pk);
  try {
    const rawData = await fetchDraft(draft.pk);
    const data = hydrateDraft(rawData as DraftType & { _users?: Record<number, unknown> });
    setDraft(data);
    log.debug('Updated Draft information');
  } catch (error) {
    log.error(error);
  }
};
