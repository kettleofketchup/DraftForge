import { useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';

import type { SearchUserResult } from '~/components/api/api';
import {
  getSpotTransferRefusal,
  type SpotTransferRefusal,
  type SpotTransferResponse,
} from '~/components/api/eventsAPI';
import { isStaffReasonRequiredError } from '~/components/api/overridesAPI';
import { Badge } from '~/components/ui/badge';
import { PrimaryButton, SecondaryButton } from '~/components/ui/buttons';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { DisplayName } from '~/components/user/avatar';
import { UserPicker } from '~/components/user/search';
import { UserAvatar } from '~/components/user/UserAvatar';
import type { useSignupActionMutations } from '~/hooks/useEvent';
import { useUserSearch } from '~/hooks/useUserSearch';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';

import { signupStatusLabel } from './EventStateBadge';
import type { EventSignupType, EventType } from './schemas';
import { isRemovedSignup } from './signupPartitions';
import { swapWouldDemoteRecipient } from './spotTransferRank';
import { unmetLabel } from './unmetRequirements';
import type { SignupOverride } from './useSignupOverride';
import type { StaffAction } from './useStaffAction';

const log = getLogger('events.transferSpot');

const DEMOTE_MESSAGE =
  'You can only swap with someone whose place is behind yours';
const MANUAL_APPROVAL_NOTE = 'Staff will need to approve them.';
const FAILURE = 'Failed to transfer place';

type Candidate = SearchUserResult & { pk: number };

/** Keep this mounted and drive `open`: staff override retries finish after it closes. */
export interface TransferSpotDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  signup: EventSignupType;
  event: EventType;
  signups: EventSignupType[];
  mode: 'member' | 'staff';
  orgId?: number;
  transfer: ReturnType<typeof useSignupActionMutations>['transfer'];
  staffAction?: StaffAction;
  signupOverride?: SignupOverride;
  onTransferred?: (response: SpotTransferResponse) => void;
}

function placeLabel(row: EventSignupType): string {
  const status = signupStatusLabel(row.status);
  return row.line_rank != null ? `#${row.line_rank}, ${status}` : status;
}

function holdsPlace(row: EventSignupType | undefined): row is EventSignupType {
  return !!row && !isRemovedSignup(row.status);
}

function successMessage(
  mode: 'member' | 'staff',
  response: SpotTransferResponse,
): string {
  const recipient = DisplayName(response.recipient);
  const giver = DisplayName(response.giver);
  if (mode === 'member')
    return response.mode === 'swap'
      ? `You swapped places with ${recipient}`
      : `You gave your place to ${recipient}`;
  return response.mode === 'swap'
    ? `Swapped ${giver} and ${recipient}`
    : `Gave ${giver}'s place to ${recipient}`;
}

export function TransferSpotDialog({
  open,
  onOpenChange,
  signup,
  event,
  signups,
  mode,
  orgId,
  transfer,
  staffAction,
  signupOverride,
  onTransferred,
}: TransferSpotDialogProps) {
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState<Candidate | null>(null);
  const [refusal, setRefusal] = useState<SpotTransferRefusal | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const armed = useRef(new Map<number, number>());
  const handledAt = useRef<number | null>(null);
  const staff = mode === 'staff';

  useEffect(() => {
    if (!open) return;
    setQuery('');
    setPicked(null);
    setRefusal(null);
  }, [open]);

  const search = useUserSearch(query, {
    orgId: staff ? orgId : undefined,
    enabled: open,
  });

  useEffect(() => {
    if (search.status === 'error')
      log.error('Recipient search failed', { error: search.error });
  }, [search.status, search.error]);

  const candidates = useMemo<Candidate[]>(() => {
    const list = search.results.filter(
      (u): u is Candidate => u.pk != null && u.pk !== signup.user,
    );
    if (!staff) return list;
    const members = list.filter((u) => u.membership === 'org');
    return [...members, ...list.filter((u) => u.membership !== 'org')];
  }, [search.results, signup.user, staff]);

  const rowByUser = useMemo(
    () => new Map(signups.map((s) => [s.user, s])),
    [signups],
  );

  const { data, status, submittedAt } = transfer;
  useEffect(() => {
    if (status !== 'success' || !data) return;
    const since = armed.current.get(data.giver.id);
    if (since === undefined || submittedAt < since) return;
    if (handledAt.current === submittedAt) return;
    handledAt.current = submittedAt;
    armed.current.delete(data.giver.id);
    log.info('Spot transferred', {
      signupId: data.giver.id,
      mode: data.mode,
      correlationId: data.correlation_id,
    });
    toast.success(successMessage(mode, data));
    onTransferred?.(data);
    if (data.giver.id === signup.id) onOpenChange(false);
  }, [data, status, submittedAt, mode, onTransferred, onOpenChange, signup.id]);

  const giverName = staff ? DisplayName(signup) : null;
  const theirRow = picked ? rowByUser.get(picked.pk) : undefined;
  const swap = holdsPlace(theirRow);
  const blocked = !staff && swap && swapWouldDemoteRecipient(signup, theirRow);
  const pickedName = picked ? DisplayName(picked) : '';

  const copy = (() => {
    if (!picked) return '';
    const mine = placeLabel(signup);
    if (swap) {
      const theirs = placeLabel(theirRow);
      return staff
        ? `Swap ${giverName} and ${pickedName}? ${giverName} takes ${pickedName}'s place (${theirs}) and ${pickedName} takes ${giverName}'s place (${mine}).`
        : `Swap places with ${pickedName}? You take their place (${theirs}) and they take yours (${mine}).`;
    }
    return staff
      ? `Give ${giverName}'s place (${mine}) to ${pickedName}? ${giverName} will be withdrawn.`
      : `Give your place (${mine}) to ${pickedName}? You will be withdrawn. This can't be undone by you.`;
  })();

  const showRefusal = (error: unknown) => {
    const parsed = getSpotTransferRefusal(error);
    if (parsed) {
      log.warn('Spot transfer refused', { code: parsed.code });
      setRefusal(parsed);
      return;
    }
    log.warn('Spot transfer failed', { error: extractApiError(error) });
    toast.error(extractApiError(error) ?? FAILURE);
  };

  const runStaff = async (recipientUserId: number) => {
    if (!staffAction || !signupOverride) {
      log.error('Staff transfer opened without staff handlers', {
        signupId: signup.id,
      });
      return;
    }
    const send = signupOverride.fire('transfer', signup.id, giverName ?? '', {
      recipientUserId,
    });
    const collect = (forceRequired = false) =>
      staffAction.collect('transfer', {
        userId: signup.user,
        title: 'Transfer place',
        forceRequired,
      });
    let reason = await collect();
    if (reason === null) {
      armed.current.delete(signup.id);
      return;
    }
    try {
      await send(reason);
    } catch (error) {
      if (!isStaffReasonRequiredError(error)) throw error;
      reason = await collect(true);
      if (reason === null) {
        armed.current.delete(signup.id);
        return;
      }
      await send(reason);
    }
    onOpenChange(false);
  };

  const confirm = async () => {
    if (!picked || blocked || submitting) return;
    setRefusal(null);
    setSubmitting(true);
    armed.current.set(signup.id, Date.now());
    log.info('Spot transfer requested', {
      signupId: signup.id,
      mode,
      swap,
    });
    try {
      if (staff) await runStaff(picked.pk);
      else
        await transfer.mutateAsync({
          id: signup.id,
          recipient_user_id: picked.pk,
        });
    } catch (error) {
      armed.current.delete(signup.id);
      showRefusal(error);
    } finally {
      setSubmitting(false);
    }
  };

  const busy = submitting || transfer.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="transfer-spot-dialog">
        <DialogHeader>
          <DialogTitle>
            {staff ? 'Transfer place' : 'Give your place'}
          </DialogTitle>
          <DialogDescription data-testid="transfer-spot-current">
            {staff
              ? `${giverName}'s place: ${placeLabel(signup)}`
              : `Your place: ${placeLabel(signup)}`}
          </DialogDescription>
        </DialogHeader>

        {picked ? (
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <UserAvatar user={picked} size="sm" />
              <span className="font-medium">{pickedName}</span>
              <SecondaryButton
                size="sm"
                className="ml-auto"
                data-testid="transfer-spot-change"
                onClick={() => {
                  setPicked(null);
                  setRefusal(null);
                }}
                disabled={busy}
              >
                Change
              </SecondaryButton>
            </div>
            {blocked ? (
              <p
                className="text-sm text-warning"
                data-testid="transfer-spot-demote"
              >
                {DEMOTE_MESSAGE}
              </p>
            ) : (
              <p className="text-sm" data-testid="transfer-spot-copy">
                {copy}
              </p>
            )}
            {!staff && !swap && !blocked && !event.auto_approve ? (
              <p
                className="text-sm text-muted-foreground"
                data-testid="transfer-spot-approval-note"
              >
                {MANUAL_APPROVAL_NOTE}
              </p>
            ) : null}
            {refusal ? (
              <div
                className="rounded-md border border-error/30 bg-error/10 p-3 text-sm"
                data-testid="transfer-spot-refusal"
                role="alert"
              >
                {refusal.code === 'recipient_ineligible' &&
                refusal.reasons.length ? (
                  <>
                    <p>{pickedName} can&apos;t take this place:</p>
                    <ul
                      className="mt-1 list-disc pl-5"
                      data-testid="transfer-spot-reasons"
                    >
                      {refusal.reasons.map((r) => (
                        <li key={`${r.rule}:${r.code}`}>
                          {unmetLabel(r.code, r.message)}
                        </li>
                      ))}
                    </ul>
                  </>
                ) : (
                  <p>{refusal.error}</p>
                )}
              </div>
            ) : null}
          </div>
        ) : (
          <UserPicker
            query={query}
            onQueryChange={setQuery}
            results={candidates}
            status={search.status}
            onSelect={(u) => {
              setPicked(u);
              setRefusal(null);
            }}
            renderBadge={(u) => {
              const held = rowByUser.get(u.pk);
              return (
                <>
                  {staff && u.membership === 'org' ? (
                    <Badge variant="outline">Member</Badge>
                  ) : null}
                  {holdsPlace(held) && held.line_rank != null ? (
                    <Badge variant="outline">
                      has a place (#{held.line_rank})
                    </Badge>
                  ) : null}
                </>
              );
            }}
            placeholder={staff ? 'Search members by name' : 'Search by name'}
            ariaLabel="Search for the person to give the place to"
            emptyMessage="No one matches."
            errorMessage={extractApiError(search.error) ?? 'Search failed'}
            className="rounded-md border"
            listClassName="max-h-72"
            testIds={{
              input: 'transfer-spot-search',
              results: 'transfer-spot-results',
              option: (u) => `transfer-spot-option-${u.pk}`,
              hint: 'transfer-spot-hint',
              searching: 'transfer-spot-searching',
              empty: 'transfer-spot-empty',
              error: 'transfer-spot-error',
            }}
          />
        )}

        <DialogFooter>
          <SecondaryButton
            onClick={() => onOpenChange(false)}
            data-testid="transfer-spot-cancel"
          >
            Cancel
          </SecondaryButton>
          <PrimaryButton
            onClick={() => void confirm()}
            disabled={!picked || blocked || busy}
            data-testid="transfer-spot-confirm"
          >
            {swap ? 'Swap places' : staff ? 'Transfer' : 'Give place'}
          </PrimaryButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
