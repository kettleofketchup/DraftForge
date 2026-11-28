import { useCallback, useState, type ReactNode, type RefObject } from 'react';
import { toast } from 'sonner';

import { useOrganization } from '~/components/organization/hooks/useOrganization';
import type { SettingsDialogHandle } from '~/components/patterns/SettingsDialog';
import type { SettingsFormUnit } from '~/components/patterns/settingsSaveBar';
import { ApiAccessPanel } from '~/features/api-tokens';
import type { ConnectionDraftState } from '~/features/api-tokens/ApiAccessPanel';
import { useOrgFeatureAccess } from '~/features/org-features';

const SECTION_ID = 'api-access';

/**
 * The connection editor saves on its own; the host save bar only learns that
 * a draft is open so closing or navigating away asks before discarding it.
 */
export function useApiAccessSection(
  organizationId: number,
  enabled: boolean,
  sectionsRef?: RefObject<SettingsDialogHandle<string> | null>,
): { content: ReactNode; unit: SettingsFormUnit } {
  const { organization } = useOrganization(
    enabled ? organizationId : undefined,
  );
  const access = useOrgFeatureAccess(organization ?? undefined);
  const scope = `${organizationId}:${access.viewerPk ?? 'anon'}`;
  const [scopedDraft, setScopedDraft] = useState<{
    scope: string;
    state: ConnectionDraftState;
  } | null>(null);
  const draft = scopedDraft?.scope === scope ? scopedDraft.state : null;
  const onConnectionDraftChange = useCallback(
    (state: ConnectionDraftState) => setScopedDraft({ scope, state }),
    [scope],
  );
  const unit: SettingsFormUnit = {
    id: SECTION_ID,
    isDirty: enabled && Boolean(draft?.dirty),
    save: async (opts) => {
      if (opts?.select !== false) {
        sectionsRef?.current?.selectSection(SECTION_ID);
      }
      toast.info('Save or discard the open API connection in its dialog.');
      return false;
    },
    discard: () => draft?.discard(),
  };
  return {
    content: (
      <ApiAccessPanel
        key={scope}
        orgId={organizationId}
        access={access}
        enabled={enabled}
        onConnectionDraftChange={onConnectionDraftChange}
        memberCount={organization?.users_count ?? null}
      />
    ),
    unit,
  };
}
