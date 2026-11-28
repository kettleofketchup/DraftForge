import { useCallback, useRef, useState } from 'react';

import {
  getOverrideRequired,
  isOverrideReasonRequiredError,
  NO_ACKNOWLEDGEMENT,
  type OverrideAcknowledgement,
  type OverrideRequired,
} from '~/components/api/overridesAPI';
import { getLogger } from '~/lib/logger';

const log = getLogger('useOverrideRetry');

export interface UseOverrideRetryOptions<T> {
  onSuccess?: (result: T) => void;
  onError?: (err: unknown) => void;
  rethrow?: boolean;
}

export interface OverrideDialogBinding {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  override: OverrideRequired | null;
  onConfirm: (reason: string) => Promise<void>;
  submitting: boolean;
  reasonError: string | null;
}

export type OverrideRunOutcome = 'done' | 'override';

export interface UseOverrideRetry<C = void> {
  run: (ctx: C) => Promise<OverrideRunOutcome>;
  pending: boolean;
  dialogProps: OverrideDialogBinding;
}

const REASON_REJECTED = 'A reason (1-500 characters) is required.';

export function useOverrideRetry<T, C = void>(
  action: (ack: OverrideAcknowledgement, ctx: C) => Promise<T>,
  options: UseOverrideRetryOptions<T> = {},
): UseOverrideRetry<C> {
  const [override, setOverride] = useState<OverrideRequired | null>(null);
  const [pending, setPending] = useState(false);
  const [reasonError, setReasonError] = useState<string | null>(null);
  const acknowledged = useRef<string[]>([]);
  const runArgs = useRef<[C] | []>([]);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const attempt = useCallback(
    async (
      ack: OverrideAcknowledgement,
      fromRun: boolean,
    ): Promise<OverrideRunOutcome> => {
      setPending(true);
      try {
        const result = await action(ack, ...(runArgs.current as [C]));
        setOverride(null);
        setReasonError(null);
        acknowledged.current = [];
        optionsRef.current.onSuccess?.(result);
        return 'done';
      } catch (err) {
        const required = getOverrideRequired(err);
        if (required) {
          log.info('Override required', {
            blocked: required.blocked,
            codes: required.violations.map((v) => v.code),
          });
          setReasonError(null);
          setOverride(required);
          return 'override';
        }
        if (
          isOverrideReasonRequiredError(err) &&
          ack.acknowledged_codes.length
        ) {
          setReasonError(REASON_REJECTED);
          return 'override';
        }
        setOverride(null);
        if (fromRun && optionsRef.current.rethrow) throw err;
        optionsRef.current.onError?.(err);
        return 'done';
      } finally {
        setPending(false);
      }
    },
    [action],
  );

  const run = useCallback(
    (...args: [ctx: C]) => {
      runArgs.current = args;
      acknowledged.current = [];
      return attempt(NO_ACKNOWLEDGEMENT, true);
    },
    [attempt],
  );

  const onConfirm = useCallback(
    async (reason: string) => {
      if (!override || override.blocked) return;
      const codes = [
        ...acknowledged.current,
        ...override.violations.map((v) => v.code),
      ];
      acknowledged.current = [...new Set(codes)];
      await attempt(
        { acknowledged_codes: acknowledged.current, reason },
        false,
      );
    },
    [attempt, override],
  );

  const onOpenChange = useCallback((open: boolean) => {
    if (open) return;
    setOverride(null);
    setReasonError(null);
    acknowledged.current = [];
  }, []);

  return {
    run,
    pending,
    dialogProps: {
      open: override !== null,
      onOpenChange,
      override,
      onConfirm,
      submitting: pending,
      reasonError,
    },
  };
}
