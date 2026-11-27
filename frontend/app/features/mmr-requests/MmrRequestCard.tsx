import { Check, Clock, ImageOff, Undo2, X } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { computeMmrDelta } from '~/components/game/mmrDelta';
import { Badge } from '~/components/ui/badge';
import { ConfirmButton, DestructiveButton } from '~/components/ui/buttons';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { Label } from '~/components/ui/label';
import { Textarea } from '~/components/ui/textarea';
import { UserAvatar } from '~/components/user/UserAvatar';
import { cn } from '~/lib/utils';
import {
  formatMmrDate,
  screenshotRemovedLabel,
  requestTargetLabel as targetLabel,
} from './format';
import { useRejectMmrRequest } from './queries';
import type { MmrScope } from './queryKeys';
import { reviewErrorMessage } from './reviewErrors';
import { ReviewMmrDialog } from './ReviewMmrDialog';
import {
  TEXT_MAX_LENGTH,
  type MmrChangeRequest,
  type MmrRequestStatus,
} from './schemas';

export interface MmrRequestCardProps {
  request: MmrChangeRequest;
  scope: MmrScope;
}

const STATUS_BADGE: Record<
  MmrRequestStatus,
  { label: string; className: string; icon: typeof Clock }
> = {
  pending: {
    label: 'Pending',
    className: 'bg-warning text-warning-foreground',
    icon: Clock,
  },
  approved: {
    label: 'Approved',
    className: 'bg-success text-success-foreground',
    icon: Check,
  },
  rejected: {
    label: 'Rejected',
    className: 'bg-error text-error-foreground',
    icon: X,
  },
  superseded: {
    label: 'Superseded',
    className: 'bg-muted text-muted-foreground',
    icon: Undo2,
  },
  cancelled: {
    label: 'Cancelled',
    className: 'bg-muted text-muted-foreground',
    icon: X,
  },
};

function StatusBadge({ status }: { status: MmrRequestStatus }) {
  const { label, className, icon: Icon } = STATUS_BADGE[status];
  return (
    <Badge className={cn('gap-1 border-transparent', className)}>
      <Icon className="size-3" aria-hidden />
      {label}
    </Badge>
  );
}

function Screenshot({ request }: { request: MmrChangeRequest }) {
  const [failed, setFailed] = useState(false);
  const [enlarged, setEnlarged] = useState(false);
  const url = request.has_screenshot ? request.screenshot_url : null;

  if (!url || failed) {
    return (
      <div
        className="flex h-24 w-36 shrink-0 flex-col items-center justify-center gap-1 rounded-md border border-dashed border-border text-xs text-muted-foreground"
        data-testid={`mmr-card-no-screenshot-${request.id}`}
      >
        <ImageOff className="size-4" aria-hidden />
        {request.screenshot_purged_at
          ? screenshotRemovedLabel(request)
          : request.source === 'staff' && !request.has_screenshot
            ? 'No screenshot'
            : 'Screenshot unavailable'}
      </div>
    );
  }

  return (
    <>
      <button
        type="button"
        className="h-24 w-36 shrink-0 overflow-hidden rounded-md border border-border bg-base-300 p-0"
        onClick={() => setEnlarged(true)}
        aria-label="Enlarge screenshot"
        data-testid={`mmr-card-screenshot-${request.id}`}
      >
        <img
          src={url}
          alt="MMR screenshot"
          className="size-full object-cover"
          loading="lazy"
          onError={() => setFailed(true)}
        />
      </button>
      <Dialog open={enlarged} onOpenChange={setEnlarged}>
        <DialogContent className="sm:max-w-4xl">
          <DialogHeader>
            <DialogTitle>Screenshot</DialogTitle>
            <DialogDescription>{targetLabel(request)}</DialogDescription>
          </DialogHeader>
          <img
            src={url}
            alt="MMR screenshot"
            className="max-h-[75svh] w-full object-contain"
            onError={() => setFailed(true)}
            data-testid={`mmr-card-screenshot-large-${request.id}`}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}

function Outcome({ request }: { request: MmrChangeRequest }) {
  const date = formatMmrDate(request.reviewed_at);
  const by = request.reviewed_by_username;
  const when = [by && `by ${by}`, date && `on ${date}`]
    .filter(Boolean)
    .join(' ');
  const suffix = when ? ` ${when}` : '';

  switch (request.status) {
    case 'approved': {
      const value = request.approved_mmr ?? request.requested_mmr;
      const text =
        request.source === 'staff'
          ? `Set as official${suffix}`
          : value !== request.requested_mmr
            ? `Approved as ${value}${suffix}`
            : `Approved${suffix}`;
      return <p data-testid={`mmr-card-outcome-${request.id}`}>{text}</p>;
    }
    case 'rejected':
      return (
        <p data-testid={`mmr-card-outcome-${request.id}`}>
          Rejected{suffix}
          {request.rejection_reason && (
            <span className="text-error">: {request.rejection_reason}</span>
          )}
        </p>
      );
    case 'superseded':
      return (
        <p data-testid={`mmr-card-outcome-${request.id}`}>
          Replaced by an official value of {request.approved_mmr ?? '—'}
          {suffix}
        </p>
      );
    case 'cancelled':
      return (
        <p data-testid={`mmr-card-outcome-${request.id}`}>
          Cancelled by the member
        </p>
      );
    default:
      return null;
  }
}

export function MmrRequestCard({ request, scope }: MmrRequestCardProps) {
  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState('');
  const reject = useRejectMmrRequest();

  const pending = request.status === 'pending';
  const base = pending ? request.current_mmr : request.previous_mmr;
  const delta = computeMmrDelta(base, request.requested_mmr);
  const name = request.subject.nickname || request.subject.username;
  const trimmedReason = reason.trim();
  const showOrg = 'league' in scope;

  const handleReject = async () => {
    try {
      await reject.mutateAsync({ request, reason: trimmedReason });
      toast.success(`Rejected ${name}'s request`);
      setReason('');
    } catch (error) {
      toast.error(reviewErrorMessage(error, 'Could not reject the request'));
    }
  };

  return (
    <div
      className="card-3d rounded-[1.25rem] bg-base-300 p-4 transition-colors hover:bg-base-200 md:p-6"
      data-testid={`mmr-card-${request.id}`}
    >
      <div className="flex flex-col gap-4 md:flex-row">
        <Screenshot request={request} />

        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <div className="flex flex-wrap items-center gap-3">
            <UserAvatar
              user={request.subject}
              src={request.subject.avatarUrl ?? undefined}
              size="lg"
            />
            <div className="min-w-0 flex-1">
              <div className="truncate font-medium">{name}</div>
              <div
                className="text-sm text-muted-foreground"
                data-testid={`mmr-card-target-${request.id}`}
              >
                {targetLabel(request)}
                {showOrg && ` · ${request.organization.name}`}
              </div>
            </div>
            <StatusBadge status={request.status} />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span
              className="font-mono text-lg"
              data-testid={`mmr-card-mmrs-${request.id}`}
            >
              {base > 0 ? base : 'Not set'} → {request.requested_mmr}
            </span>
            {delta.delta !== 0 && (
              <span
                data-testid={`mmr-card-delta-${request.id}`}
                className={cn(
                  'rounded-md border px-2 py-0.5 font-mono text-xs',
                  delta.isLarge
                    ? 'border-warning/40 bg-warning/5 text-warning'
                    : 'border-border/60 bg-base-200 text-muted-foreground',
                )}
              >
                {delta.delta > 0 ? '+' : ''}
                {delta.delta}
                {delta.pct != null && `, ${Math.round(delta.pct * 100)}%`}
              </span>
            )}
          </div>

          {request.note && (
            <p
              className="text-sm whitespace-pre-wrap break-words"
              data-testid={`mmr-card-note-${request.id}`}
            >
              “{request.note}”
            </p>
          )}

          <div className="text-sm text-muted-foreground">
            <p>
              {request.source === 'staff'
                ? `Set by ${request.requester_username}`
                : 'Requested'}{' '}
              {formatMmrDate(request.created_at)}
            </p>
            <Outcome request={request} />
          </div>

          {pending &&
            (request.can_review ? (
              <div className="flex flex-wrap gap-2">
                <ConfirmButton
                  size="sm"
                  variant="success"
                  onClick={() => setApproveOpen(true)}
                  data-testid={`mmr-approve-btn-${request.id}`}
                >
                  <Check className="mr-1 size-4" />
                  Approve
                </ConfirmButton>
                <DestructiveButton
                  size="sm"
                  onClick={() => setRejectOpen(true)}
                  data-testid={`mmr-reject-btn-${request.id}`}
                >
                  <X className="mr-1 size-4" />
                  Reject
                </DestructiveButton>
              </div>
            ) : (
              <p
                className="text-sm text-muted-foreground italic"
                data-testid={`mmr-needs-admin-${request.id}`}
              >
                Needs another admin to review
              </p>
            ))}
        </div>
      </div>

      {pending && request.can_review && (
        <>
          <ReviewMmrDialog
            request={request}
            open={approveOpen}
            onOpenChange={setApproveOpen}
          />
          <ConfirmDialog
            open={rejectOpen}
            onOpenChange={setRejectOpen}
            title="Reject MMR request"
            description={`Reject ${name}'s request to set ${targetLabel(request)} to ${request.requested_mmr}. They will see your reason on their profile.`}
            confirmLabel="Reject"
            variant="destructive"
            isLoading={reject.isPending}
            confirmDisabled={
              trimmedReason.length === 0 ||
              trimmedReason.length > TEXT_MAX_LENGTH
            }
            onConfirm={handleReject}
            confirmTestId="mmr-reject-confirm"
            bodyContent={
              <div className="flex flex-col gap-2">
                <Label htmlFor={`mmr-reject-reason-${request.id}`}>
                  Reason *
                </Label>
                <Textarea
                  id={`mmr-reject-reason-${request.id}`}
                  rows={2}
                  maxLength={TEXT_MAX_LENGTH}
                  placeholder="e.g. The screenshot doesn't show the rank"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  disabled={reject.isPending}
                  data-testid="mmr-reject-reason"
                />
              </div>
            }
          />
        </>
      )}
    </div>
  );
}
