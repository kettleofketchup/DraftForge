import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { ScrollArea } from '~/components/ui/scroll-area';
import { UserAvatar } from '~/components/user/UserAvatar';
import { DisplayName } from '~/components/user/avatar';
import type { OrgFeatureAccess } from '~/features/org-features';
import { ComposePanel } from './ComposePanel';
import { mmrLabel, type ComposeMode } from './promotionColumns';
import type {
  LinkedCandidate,
  PromoEvent,
  PromoSendResult,
  PromoTemplate,
} from './schemas';

export interface PromotionComposer {
  candidate: LinkedCandidate;
  mode: ComposeMode;
}

export interface PromotionMessageDialogProps {
  orgId: number;
  access: OrgFeatureAccess;
  event: PromoEvent;
  composer: PromotionComposer | null;
  templates: PromoTemplate[];
  gameLabel: string;
  onClose: () => void;
  onSent: (send: PromoSendResult | null) => void;
}

const TITLE: Record<ComposeMode, string> = {
  message: 'Message',
  record: 'Record a message to',
};

/** One recipient at a time: compose or record a promotion DM for an event. */
export function PromotionMessageDialog({
  orgId,
  access,
  event,
  composer,
  templates,
  gameLabel,
  onClose,
  onSent,
}: PromotionMessageDialogProps) {
  return (
    <Dialog
      open={composer != null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      {composer && (
        <DialogContent
          className="flex max-h-[90vh] flex-col overflow-hidden sm:max-w-2xl"
          closeButtonTestId="promo-dialog-close"
          data-testid="promo-message-dialog"
        >
          <DialogHeader>
            <div className="flex items-center gap-3 pr-8">
              <UserAvatar
                user={{ ...composer.candidate, pk: composer.candidate.user_pk }}
                size="md"
              />
              <div className="flex min-w-0 flex-col gap-1 text-left">
                <DialogTitle className="wrap-anywhere">
                  {TITLE[composer.mode]} {DisplayName(composer.candidate)}
                </DialogTitle>
                <DialogDescription data-testid="promo-dialog-description">
                  For {event.name} · {gameLabel} MMR{' '}
                  {mmrLabel(composer.candidate.mmr)}
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>
          <ScrollArea className="min-h-0 flex-1 -mx-6 px-6">
            <div className="pb-2">
              <ComposePanel
                key={`${event.id}-${composer.candidate.user_pk}-${composer.mode}`}
                orgId={orgId}
                access={access}
                event={event}
                candidate={composer.candidate}
                templates={templates}
                onSent={onSent}
                mode={composer.mode}
                embedded
              />
            </div>
          </ScrollArea>
        </DialogContent>
      )}
    </Dialog>
  );
}
