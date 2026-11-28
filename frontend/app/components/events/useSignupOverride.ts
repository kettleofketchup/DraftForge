import { useCallback, useState } from 'react';
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

export type SignupOverrideKind = 'void_withdrawal' | 'reinstate';

type SignupOverrideContext = {
  kind: SignupOverrideKind;
  id: number;
  reason?: string;
};

export interface SignupOverride {
  fire: (
    kind: SignupOverrideKind,
    id: number,
  ) => (reason?: string) => Promise<void>;
  dialogProps: OverrideDialogBinding & { defaultReason: string };
}

export function useSignupOverride(
  signupActions: ReturnType<typeof useSignupActionMutations>,
): SignupOverride {
  const voidWithdrawal = signupActions.voidWithdrawal.mutateAsync;
  const reinstate = signupActions.reinstate.mutateAsync;
  const [defaultReason, setDefaultReason] = useState('');

  const action = useCallback(
    (ack: OverrideAcknowledgement, ctx: SignupOverrideContext) => {
      const reason = ack.reason ?? ctx.reason;
      return (ctx.kind === 'void_withdrawal' ? voidWithdrawal : reinstate)({
        id: ctx.id,
        ...(reason ? { reason } : {}),
        ...(ack.acknowledged_codes.length
          ? { acknowledged_codes: ack.acknowledged_codes }
          : {}),
      });
    },
    [voidWithdrawal, reinstate],
  );

  const { run, dialogProps } = useOverrideRetry(action, {
    rethrow: true,
    onError: (error) => {
      log.warn('Signup override retry failed', {
        error: extractApiError(error),
      });
      toast.error(extractApiError(error) ?? 'Failed to restore signup');
    },
  });

  const fire = useCallback(
    (kind: SignupOverrideKind, id: number) =>
      async (reason?: string): Promise<void> => {
        setDefaultReason(reason ?? '');
        await run({ kind, id, ...(reason ? { reason } : {}) });
      },
    [run],
  );

  return { fire, dialogProps: { ...dialogProps, defaultReason } };
}
