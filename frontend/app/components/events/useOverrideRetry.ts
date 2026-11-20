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
}

export interface OverrideDialogBinding {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  override: OverrideRequired | null;
  onConfirm: (reason: string) => Promise<void>;
  submitting: boolean;
  reasonError: string | null;
}

export interface UseOverrideRetry {
  run: () => Promise<void>;
  pending: boolean;
  dialogProps: OverrideDialogBinding;
}

const REASON_REJECTED = 'A reason (1-500 characters) is required.';

export function useOverrideRetry<T>(
  action: (ack: OverrideAcknowledgement) => Promise<T>,
  options: UseOverrideRetryOptions<T> = {},
): UseOverrideRetry {
  const [override, setOverride] = useState<OverrideRequired | null>(null);
  const [pending, setPending] = useState(false);
  const [reasonError, setReasonError] = useState<string | null>(null);
  const acknowledged = useRef<string[]>([]);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const attempt = useCallback(
    async (ack: OverrideAcknowledgement) => {
      setPending(true);
      try {
        const result = await action(ack);
        setOverride(null);
        setReasonError(null);
        acknowledged.current = [];
        optionsRef.current.onSuccess?.(result);
      } catch (err) {
        const required = getOverrideRequired(err);
        if (required) {
          log.info('Override required', {
            blocked: required.blocked,
            codes: required.violations.map((v) => v.code),
          });
          setReasonError(null);
          setOverride(required);
        } else if (
          isOverrideReasonRequiredError(err) &&
          ack.acknowledged_codes.length
        ) {
          setReasonError(REASON_REJECTED);
        } else {
          setOverride(null);
          optionsRef.current.onError?.(err);
        }
      } finally {
        setPending(false);
      }
    },
    [action],
  );

  const run = useCallback(() => {
    acknowledged.current = [];
    return attempt(NO_ACKNOWLEDGEMENT);
  }, [attempt]);

  const onConfirm = useCallback(
    async (reason: string) => {
      if (!override || override.blocked) return;
      const codes = [
        ...acknowledged.current,
        ...override.violations.map((v) => v.code),
      ];
      acknowledged.current = [...new Set(codes)];
      await attempt({ acknowledged_codes: acknowledged.current, reason });
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
