import { fetchDraft } from '~/components/api/api';
import type { DraftType } from '~/index';
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
    const data: DraftType = await fetchDraft(draft.pk);
    setDraft(data);
    log.debug('Updated Draft information');
  } catch (error) {
    log.error(error);
  }
};
