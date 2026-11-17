import { ExternalLink, Info, X } from 'lucide-react';
import { useEffect } from 'react';
import { SecondaryButton } from '~/components/ui/buttons';
import { postActivityView } from '~/lib/activity-api';
import { openExternal } from '~/lib/discord';
import { getLogger } from '~/lib/logger';
import { useActivityViewStore } from '~/store/activityViewStore';

const log = getLogger('activity');

export function ActivityNotice() {
  const notice = useActivityViewStore((s) => s.notice);
  const intentId = notice?.intent_id;

  useEffect(() => {
    if (!intentId) return;
    const { seenNoticeIntentIds } = useActivityViewStore.getState();
    if (seenNoticeIntentIds.has(intentId)) return;
    useActivityViewStore.setState({
      seenNoticeIntentIds: new Set(seenNoticeIntentIds).add(intentId),
    });
    log.info('activity notice seen', { intentId });
    postActivityView({ action: 'notice_seen', intent_id: intentId });
  }, [intentId]);

  if (!notice) return null;
  const where = notice.tournament_name ? ` in ${notice.tournament_name}` : '';

  return (
    <div
      role="status"
      data-testid="activity-notice"
      className="flex w-full min-w-0 shrink-0 items-center gap-2 border-b border-info/40 bg-info/10 px-2 py-1.5 text-sm text-foreground sm:px-4"
    >
      <Info className="size-4 shrink-0 text-info" />
      <span className="min-w-0 flex-1">
        {notice.label}
        {where} is in another tournament&apos;s Activity.
      </span>
      <SecondaryButton
        size="sm"
        className="shrink-0"
        aria-label="Open in browser"
        data-testid="activity-notice-open"
        onClick={() => void openExternal(notice.url)}
      >
        <ExternalLink className="size-4" />
        <span className="hidden sm:inline">Open in browser</span>
      </SecondaryButton>
      <SecondaryButton
        size="icon"
        className="size-8 shrink-0"
        aria-label="Dismiss"
        data-testid="activity-notice-dismiss"
        onClick={() => useActivityViewStore.getState().dismissNotice()}
      >
        <X className="size-4" />
      </SecondaryButton>
    </div>
  );
}
