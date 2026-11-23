import { toast } from 'sonner';
import { CancelButton, ConfirmButton } from '~/components/ui/buttons';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { DisplayName } from '~/components/user/avatar';
import { getLogger } from '~/lib/logger';
import { refusalCode, refusalMessage } from './errors';
import { useReleaseResults } from './queries';
import type { EventCaptainReviews } from './schemas';

const log = getLogger('ReleaseResultsDialog');

export type ReleaseTarget = {
  captains: EventCaptainReviews[];
  /** Release only these captains; otherwise every pending captain of the event. */
  explicit: boolean;
};

export interface ReleaseResultsDialogProps {
  orgId: number;
  eventId: number;
  target: ReleaseTarget | null;
  onClose: () => void;
}

export function ReleaseResultsDialog({
  orgId,
  eventId,
  target,
  onClose,
}: ReleaseResultsDialogProps) {
  const release = useReleaseResults(orgId, eventId);
  const captains = target?.captains ?? [];

  const confirm = () => {
    if (!target) return;
    release.mutate(
      {
        captains: target.explicit
          ? captains.map((c) => c.org_user_id)
          : undefined,
      },
      {
        onSuccess: (result) => {
          log.info('leadership results released', {
            orgId,
            eventId,
            released: result.released.length,
            skipped: result.skipped.length,
          });
          toast.success(
            `Released results for ${result.released.length} ${
              result.released.length === 1 ? 'captain' : 'captains'
            }.`,
          );
          onClose();
        },
        onError: (err) => {
          log.warn('release refused', {
            orgId,
            eventId,
            code: refusalCode(err),
          });
          toast.error(refusalMessage(err, 'release'));
        },
      },
    );
  };

  return (
    <Dialog
      open={target !== null}
      onOpenChange={(open) => {
        if (!open && !release.isPending) onClose();
      }}
    >
      <DialogContent data-testid="leadership-release-dialog">
        <DialogHeader className="pr-8">
          <DialogTitle>Release these results?</DialogTitle>
          <DialogDescription>
            Captains see their ratings and points once released. This cannot be
            undone.
          </DialogDescription>
        </DialogHeader>
        <ul className="flex flex-col gap-1 text-sm">
          {captains.map((captain) => (
            <li
              key={captain.org_user_id}
              className="break-words"
              data-testid={`leadership-release-dialog-${captain.org_user_id}`}
            >
              <span className="font-medium">{captain.team_name}</span>
              <span className="text-muted-foreground">
                {` · captain ${DisplayName(captain.captain)}`}
              </span>
            </li>
          ))}
        </ul>
        <DialogFooter>
          <CancelButton
            className="min-h-11 sm:min-h-9"
            onClick={onClose}
            disabled={release.isPending}
          >
            Cancel
          </CancelButton>
          <ConfirmButton
            loadingText="Releasing..."
            className="min-h-11 sm:min-h-9"
            data-testid="leadership-release-confirm"
            disabled={captains.length === 0}
            loading={release.isPending}
            onClick={confirm}
          >
            Release
          </ConfirmButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
