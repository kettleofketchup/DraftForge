import { useCallback, useRef } from 'react';
import { create } from 'zustand';
import { ConfirmDialog } from '~/components/ui/dialogs';
import type {
  ActivityDraftList,
  ActivityTeamDraftEntry,
  ActivityView,
} from '~/lib/activity-types';
import { getLogger } from '~/lib/logger';
import { useActivityViewStore } from '~/store/activityViewStore';

const log = getLogger('activity');

export const LEAVE_PAUSES = 'Leaving pauses your draft for both teams.';
export const LEAVE_DISCONNECTS =
  'The other captain will see you as disconnected.';
export const LEAVE_UNKNOWN =
  'If you are a captain here, leaving may pause the draft.';

interface PendingLeave {
  message: string;
  proceed: () => void;
  onCancel?: () => void;
}

const usePendingLeave = create<{ pending: PendingLeave | null }>(() => ({
  pending: null,
}));

function viewedEntry(
  view: ActivityView,
  drafts: ActivityDraftList,
): ActivityTeamDraftEntry | undefined {
  if (view.kind === 'hero')
    return drafts.hero_drafts.find((d) => d.id === view.id);
  if (view.kind === 'team' && drafts.team_draft?.id === view.id)
    return drafts.team_draft;
  return undefined;
}

export function leaveWarning(
  view: ActivityView | null,
  drafts: ActivityDraftList | null,
): string | null {
  if (!view || view.kind === 'bracket') return null;
  if (!drafts) return LEAVE_UNKNOWN;
  const entry = viewedEntry(view, drafts);
  if (!entry) return null;
  if (entry.role !== 'captain' || entry.status === 'finished') return null;
  if (
    view.kind === 'hero' &&
    (entry.status === 'drafting' || entry.status === 'paused')
  )
    return LEAVE_PAUSES;
  return LEAVE_DISCONNECTS;
}

export function useLeaveGuard(): (
  proceed: () => void,
  onCancel?: () => void,
) => void {
  return useCallback((proceed, onCancel) => {
    const { view, drafts } = useActivityViewStore.getState();
    const message = leaveWarning(view, drafts);
    if (!message) {
      proceed();
      return;
    }
    log.info('activity leave confirm shown', { view, message });
    usePendingLeave.setState({ pending: { message, proceed, onCancel } });
  }, []);
}

export function LeaveDraftConfirm() {
  const pending = usePendingLeave((s) => s.pending);
  const confirmed = useRef(false);

  const handleOpenChange = (open: boolean) => {
    if (open) return;
    const current = usePendingLeave.getState().pending;
    usePendingLeave.setState({ pending: null });
    if (!confirmed.current) current?.onCancel?.();
    confirmed.current = false;
  };

  const handleConfirm = () => {
    confirmed.current = true;
    pending?.proceed();
  };

  return (
    <ConfirmDialog
      open={pending !== null}
      onOpenChange={handleOpenChange}
      title="Leave this draft?"
      description={pending?.message ?? ''}
      confirmLabel="Leave"
      cancelLabel="Stay"
      variant="warning"
      onConfirm={handleConfirm}
      confirmTestId="activity-leave-confirm"
      cancelTestId="activity-leave-stay"
      contentTestId="activity-leave-dialog"
    />
  );
}
