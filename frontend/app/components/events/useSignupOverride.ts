import { useCallback } from 'react';
import { toast } from 'sonner';

import type { OverrideAcknowledgement } from '~/components/api/overridesAPI';
import type { useSignupActionMutations } from '~/hooks/useEvent';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import {
  useOverrideRetry,
  type OverrideDialogBinding,
} from './useOverrideRetry';

const log = getLogger('events.void');

export type SignupOverrideKind = 'void_withdrawal' | 'reinstate' | 'transfer';

type SignupOverrideContext = {
  kind: SignupOverrideKind;
  id: number;
  name?: string;
  reason?: string;
  recipientUserId?: number;
};

export interface SignupOverrideExtra {
  recipientUserId?: number;
}

const FAILURE: Record<SignupOverrideKind, string> = {
  void_withdrawal: 'Failed to void withdrawal',
  reinstate: 'Failed to restore signup',
  transfer: 'Failed to transfer place',
};

function subjectFor(ctx: SignupOverrideContext): string | undefined {
  if (!ctx.name) return undefined;
  switch (ctx.kind) {
    case 'void_withdrawal':
      return `voiding ${ctx.name}'s withdrawal`;
    case 'reinstate':
      return `restoring ${ctx.name}`;
    case 'transfer':
      return `transferring ${ctx.name}'s place`;
  }
}

export interface SignupOverride {
  fire: (
    kind: SignupOverrideKind,
    id: number,
    name?: string,
    extra?: SignupOverrideExtra,
  ) => (reason?: string) => Promise<void>;
  dialogProps: OverrideDialogBinding & {
    defaultReason: string;
    subject?: string;
  };
}

export function useSignupOverride(
  signupActions: ReturnType<typeof useSignupActionMutations>,
): SignupOverride {
  const voidWithdrawal = signupActions.voidWithdrawal.mutateAsync;
  const reinstate = signupActions.reinstate.mutateAsync;
  const transfer = signupActions.transfer.mutateAsync;

  const action = useCallback(
    (
      ack: OverrideAcknowledgement,
      ctx: SignupOverrideContext,
    ): Promise<unknown> => {
      const reason = ack.reason ?? ctx.reason;
      const vars = {
        id: ctx.id,
        ...(reason ? { reason } : {}),
        ...(ack.acknowledged_codes.length
          ? { acknowledged_codes: ack.acknowledged_codes }
          : {}),
      };
      switch (ctx.kind) {
        case 'void_withdrawal':
          return voidWithdrawal(vars);
        case 'reinstate':
          return reinstate(vars);
        case 'transfer':
          if (ctx.recipientUserId === undefined)
            return Promise.reject(new Error('Transfer has no recipient'));
          return transfer({ ...vars, recipient_user_id: ctx.recipientUserId });
      }
    },
    [voidWithdrawal, reinstate, transfer],
  );

  const { run, dialogProps, context } = useOverrideRetry(action, {
    rethrow: true,
    onError: (error, ctx) => {
      log.warn('Signup override retry failed', {
        kind: ctx.kind,
        signupId: ctx.id,
        error: extractApiError(error),
      });
      toast.error(extractApiError(error) ?? FAILURE[ctx.kind]);
    },
  });

  const fire = useCallback(
    (
      kind: SignupOverrideKind,
      id: number,
      name?: string,
      extra?: SignupOverrideExtra,
    ) =>
      async (reason?: string): Promise<void> => {
        await run({
          kind,
          id,
          ...(name ? { name } : {}),
          ...(reason ? { reason } : {}),
          ...(extra?.recipientUserId !== undefined
            ? { recipientUserId: extra.recipientUserId }
            : {}),
        });
      },
    [run],
  );

  return {
    fire,
    dialogProps: {
      ...dialogProps,
      defaultReason: context?.reason ?? '',
      subject: context ? subjectFor(context) : undefined,
    },
  };
}
