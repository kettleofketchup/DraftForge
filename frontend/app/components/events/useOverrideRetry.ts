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

export interface UseOverrideRetryOptions<T, C = void> {
  onSuccess?: (result: T, ctx: C) => void;
  onError?: (err: unknown, ctx: C) => void;
  rethrow?: boolean;
}

export interface OverrideDialogBinding {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  override: OverrideRequired | null;
  onConfirm: (reason: string) => Promise<void>;
  submitting: boolean;
  reasonError: string | null;
  resetKey?: number;
}

export type OverrideRunOutcome = 'done' | 'override';

export interface UseOverrideRetry<C = void> {
  run: (ctx: C) => Promise<OverrideRunOutcome>;
  pending: boolean;
  dialogProps: OverrideDialogBinding;
  context: C | null;
}

type PendingOverride<C> = {
  key: number;
  required: OverrideRequired;
  args: [C] | [];
  acknowledged: string[];
};

const REASON_REJECTED = 'A reason (1-500 characters) is required.';

// Each 409 is queued with the ctx that hit it, so concurrent runs never
// retry one action under another's override.
export function useOverrideRetry<T, C = void>(
  action: (ack: OverrideAcknowledgement, ctx: C) => Promise<T>,
  options: UseOverrideRetryOptions<NoInfer<T>, NoInfer<C>> = {},
): UseOverrideRetry<C> {
  const [queue, setQueue] = useState<PendingOverride<C>[]>([]);
  const queueRef = useRef<PendingOverride<C>[]>([]);
  const [inFlight, setInFlight] = useState(0);
  const [retrying, setRetrying] = useState(0);
  const [reasonError, setReasonError] = useState<string | null>(null);
  const nextKey = useRef(0);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const commit = useCallback((next: PendingOverride<C>[]) => {
    queueRef.current = next;
    setQueue(next);
  }, []);

  const drop = useCallback(
    (key: number) => {
      if (queueRef.current[0]?.key === key) setReasonError(null);
      commit(queueRef.current.filter((p) => p.key !== key));
    },
    [commit],
  );

  const attempt = useCallback(
    async (
      ack: OverrideAcknowledgement,
      args: [C] | [],
      entry: PendingOverride<C> | null,
    ): Promise<OverrideRunOutcome> => {
      setInFlight((n) => n + 1);
      if (entry) setRetrying((n) => n + 1);
      const ctx = args[0] as C;
      try {
        const result = await action(ack, ...(args as [C]));
        if (entry) drop(entry.key);
        optionsRef.current.onSuccess?.(result, ctx);
        return 'done';
      } catch (err) {
        const required = getOverrideRequired(err);
        if (required) {
          log.info('Override required', {
            blocked: required.blocked,
            codes: required.violations.map((v) => v.code),
          });
          if (entry) {
            setReasonError(null);
            commit(
              queueRef.current.map((p) =>
                p.key === entry.key ? { ...p, required } : p,
              ),
            );
          } else {
            commit([
              ...queueRef.current,
              {
                key: nextKey.current++,
                required,
                args,
                acknowledged: [],
              },
            ]);
          }
          return 'override';
        }
        if (entry && isOverrideReasonRequiredError(err)) {
          setReasonError(REASON_REJECTED);
          return 'override';
        }
        if (entry) drop(entry.key);
        if (!entry && optionsRef.current.rethrow) throw err;
        optionsRef.current.onError?.(err, ctx);
        return 'done';
      } finally {
        setInFlight((n) => n - 1);
        if (entry) setRetrying((n) => n - 1);
      }
    },
    [action, commit, drop],
  );

  const run = useCallback(
    (...args: [ctx: C]) => attempt(NO_ACKNOWLEDGEMENT, args, null),
    [attempt],
  );

  const active = queue[0] ?? null;

  const onConfirm = useCallback(
    async (reason: string) => {
      const head = queueRef.current[0];
      if (!head || head.required.blocked) return;
      const acknowledged = [
        ...new Set([
          ...head.acknowledged,
          ...head.required.violations.map((v) => v.code),
        ]),
      ];
      const entry = { ...head, acknowledged };
      commit(queueRef.current.map((p) => (p.key === head.key ? entry : p)));
      await attempt(
        { acknowledged_codes: acknowledged, reason },
        head.args,
        entry,
      );
    },
    [attempt, commit],
  );

  const onOpenChange = useCallback(
    (open: boolean) => {
      if (open) return;
      const head = queueRef.current[0];
      if (head) drop(head.key);
      setReasonError(null);
    },
    [drop],
  );

  const pending = inFlight > 0;
  return {
    run,
    pending,
    context: active ? (active.args[0] as C) : null,
    dialogProps: {
      open: active !== null,
      onOpenChange,
      override: active?.required ?? null,
      onConfirm,
      submitting: retrying > 0,
      reasonError,
      resetKey: active?.key,
    },
  };
}
