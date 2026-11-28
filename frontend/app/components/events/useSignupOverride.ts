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

type SignupOverrideContext = {
  id: number;
  name?: string;
  reason?: string;
};

function subjectFor(ctx: SignupOverrideContext): string | undefined {
  return ctx.name ? `voiding ${ctx.name}'s withdrawal` : undefined;
}

/** Void withdrawal with the capacity override retry; Restore never overrides. */
export interface SignupOverride {
  fire: (id: number, name?: string) => (reason?: string) => Promise<void>;
  dialogProps: OverrideDialogBinding & {
    defaultReason: string;
    subject?: string;
  };
}

export function useSignupOverride(
  signupActions: ReturnType<typeof useSignupActionMutations>,
): SignupOverride {
  const voidWithdrawal = signupActions.voidWithdrawal.mutateAsync;

  const action = useCallback(
    (ack: OverrideAcknowledgement, ctx: SignupOverrideContext) => {
      const reason = ack.reason ?? ctx.reason;
      return voidWithdrawal({
        id: ctx.id,
        ...(reason ? { reason } : {}),
        ...(ack.acknowledged_codes.length
          ? { acknowledged_codes: ack.acknowledged_codes }
          : {}),
      });
    },
    [voidWithdrawal],
  );

  const { run, dialogProps, context } = useOverrideRetry(action, {
    rethrow: true,
    onError: (error, ctx) => {
      log.warn('Signup override retry failed', {
        signupId: ctx.id,
        error: extractApiError(error),
      });
      toast.error(extractApiError(error) ?? 'Failed to void withdrawal');
    },
  });

  const fire = useCallback(
    (id: number, name?: string) =>
      async (reason?: string): Promise<void> => {
        await run({
          id,
          ...(name ? { name } : {}),
          ...(reason ? { reason } : {}),
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
