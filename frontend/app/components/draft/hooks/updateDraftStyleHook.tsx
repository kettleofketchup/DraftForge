import { toast } from 'sonner';
import { updateDraft } from '~/components/api/api';
import type { DraftType } from '~/index';
import { getLogger } from '~/lib/logger';
const log = getLogger('updateDraftStyleHook');

type hookParams = {
  draftStyle: 'snake' | 'normal' | 'shuffle';
  draft: DraftType;
};

export const updateDraftStyleHook = async ({
  draftStyle,
  draft,
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

  await toast.promise(updateDraft(draft.pk, updatedDraft), {
    loading: `Setting draft style to ${draftStyle}...`,
    success: () => {
      log.debug('Set draft style success');
      return `Draft style set to ${draftStyle}`;
    },
    error: (err) => {
      const val = err.response?.data || 'Unknown error';
      log.error('Draft has failed to set style!', err);
      return `Failed to set draft style: ${val}`;
    },
  });
};
