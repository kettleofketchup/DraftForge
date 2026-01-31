import { toast } from 'sonner';
import { updateDraft } from '~/components/api/api';
import type { DraftType } from '~/index';
import { getLogger } from '~/lib/logger';
const log = getLogger('InitDraft');

type hookParams = {
  draftStyle: 'snake' | 'normal' | 'shuffle';
  draft: DraftType;
  setDraft: (draft: DraftType) => void;
};

export const updateDraftStyleHook = async ({
  draftStyle,
  draft,
  setDraft,
}: hookParams) => {
  log.debug('Updating draft style', { draft });

  if (!draft) {
    log.error('No draft found');
    return;
  }
  if (!draft.pk) {
    log.error('No draft pk');
    return;
  }

  const updatedDraft: Partial<DraftType> = {
    pk: draft.pk,
    draft_style: draftStyle as 'snake' | 'normal' | 'shuffle',
  };
  toast.promise(updateDraft(draft.pk, updatedDraft), {
    loading: `Setting draft style to ${draftStyle}...`,
    success: (data) => {
      log.debug('Set draft style sucess, data:', data);
      setDraft(data);
      return `Draft style set to ${draftStyle}`;
    },
    error: (err) => {
      const val = err.response.data;
      log.error(' Draft has failed to set style!', err);
      return `Failed to set draft style: ${val}`;
    },
  });
};
