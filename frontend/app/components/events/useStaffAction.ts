import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { isStaffReasonRequiredError } from '~/components/api/overridesAPI';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import type { StaffReasonDialogProps } from './StaffReasonDialog';
import type { EventSignupType, StaffReasonPolicy } from './schemas';
import { staffReasonMode, type StaffSignupAction } from './staffReasonPolicy';

const log = getLogger('useStaffAction');
const REQUIRED_MESSAGE = 'A reason is required for this change.';

type Fire = (reason?: string) => Promise<unknown>;
type ActionOptions = {
  reason?: string;
  errorLabel?: string;
  title?: string;
  actionLabel?: string;
};
type Signup = Pick<EventSignupType, 'id' | 'status' | 'user'>;
type Prompt = {
  key: number;
  action: StaffSignupAction;
  signupId?: number;
  title: string;
  actionLabel: string;
  errorLabel: string;
  required: boolean;
  initialReason: string;
  serverError?: string;
  fire?: Fire;
  resolve: (reason: string | null) => void;
};

export function useStaffAction({
  policy,
  currentUserId,
}: {
  policy: StaffReasonPolicy | undefined;
  currentUserId: number | undefined;
}) {
  const [prompt, setPrompt] = useState<Prompt | null>(null);
  const active = useRef<Prompt | null>(null);
  const queued = useRef<Prompt[]>([]);
  const nextKey = useRef(0);
  const [submitting, setSubmitting] = useState(false);
  const inFlight = useRef(false);

  useEffect(
    () => () => {
      for (const p of [active.current, ...queued.current]) p?.resolve(null);
      active.current = null;
      queued.current = [];
    },
    [],
  );

  const show = (next: Prompt | null) => {
    active.current = next;
    setPrompt(next);
  };

  const finish = (reason: string | null) => {
    const current = active.current;
    show(queued.current.shift() ?? null);
    current?.resolve(reason);
  };

  const ask = (
    options: Omit<Prompt, 'resolve' | 'key'>,
    { queue = false }: { queue?: boolean } = {},
  ): Promise<string | null> => {
    if (active.current && !queue) return Promise.resolve(null);
    return new Promise((resolve) => {
      const next = { ...options, key: nextKey.current++, resolve };
      if (active.current) queued.current.push(next);
      else show(next);
    });
  };

  const promptOptions = (
    action: StaffSignupAction,
    signup: Signup,
    fire: Fire,
    opts: ActionOptions,
  ) => ({
    action,
    signupId: signup.id,
    title: opts.title ?? 'Change signup',
    actionLabel: opts.actionLabel ?? 'Confirm',
    errorLabel: opts.errorLabel ?? action.replaceAll('_', ' '),
    required:
      staffReasonMode(policy, action, {
        fromStatus: signup.status,
        isSelf: signup.user === currentUserId,
      }) === 'required',
    initialReason: opts.reason ?? '',
    fire,
  });

  const askAfterReasonRequired = (
    options: ReturnType<typeof promptOptions>,
    reason: string | undefined,
    queue: boolean,
  ) => {
    log.info('Staff reason required by server', {
      action: options.action,
      signupId: options.signupId,
    });
    return ask(
      {
        ...options,
        required: true,
        initialReason: reason ?? '',
        serverError: REQUIRED_MESSAGE,
      },
      { queue },
    );
  };

  const run = async (
    action: StaffSignupAction,
    signup: Signup,
    fire: Fire,
    opts: ActionOptions = {},
  ): Promise<boolean> => {
    if (active.current) return false;
    const options = promptOptions(action, signup, fire, opts);
    if (options.required && !opts.reason?.trim())
      return (await ask(options)) !== null;
    try {
      await fire(opts.reason);
      return true;
    } catch (error) {
      if (isStaffReasonRequiredError(error))
        return (
          (await askAfterReasonRequired(options, opts.reason, false)) !== null
        );
      toast.error(extractApiError(error) ?? `Failed to ${options.errorLabel}`);
      return false;
    }
  };

  // Resolves once the request is sent, not when it settles: a late
  // reason_required queues a recovery prompt, any other failure toasts.
  const dispatch = async (
    action: StaffSignupAction,
    signup: Signup,
    fire: Fire,
    opts: ActionOptions = {},
  ): Promise<boolean> => {
    const options = promptOptions(action, signup, fire, opts);
    let reason = opts.reason;
    if (options.required && !reason?.trim()) {
      const collected = await ask({ ...options, fire: undefined });
      if (collected === null) return false;
      reason = collected;
    }
    fire(reason).catch((error: unknown) => {
      if (isStaffReasonRequiredError(error))
        void askAfterReasonRequired(options, reason, true);
      else
        toast.error(
          extractApiError(error) ?? `Failed to ${options.errorLabel}`,
        );
    });
    return true;
  };

  const collect = (
    action: StaffSignupAction,
    target: { userId: number; title?: string; forceRequired?: boolean },
  ): Promise<string | null> =>
    ask({
      action,
      title: target.title ?? 'Change signup',
      actionLabel: 'Confirm',
      errorLabel: action.replaceAll('_', ' '),
      required:
        target.forceRequired ||
        staffReasonMode(policy, action, {
          isSelf: target.userId === currentUserId,
        }) === 'required',
      initialReason: '',
    });

  const shownKey = prompt?.key;
  const dialogProps: StaffReasonDialogProps = {
    open: prompt !== null,
    title: prompt?.title ?? 'Change signup',
    actionLabel: prompt?.actionLabel ?? 'Confirm',
    required: prompt?.required ?? false,
    destructive:
      prompt !== null && ['reject', 'cancel', 'demote'].includes(prompt.action),
    submitting,
    initialReason: prompt?.initialReason,
    serverError: prompt?.serverError,
    resetKey: shownKey,
    onOpenChange: (open) => {
      // A late close from a submitted prompt must not cancel the queued one.
      if (!open && !inFlight.current && active.current?.key === shownKey)
        finish(null);
    },
    onConfirm: async (reason) => {
      const current = active.current;
      if (!current || inFlight.current) return false;
      inFlight.current = true;
      setSubmitting(true);
      try {
        await current.fire?.(reason);
        finish(reason);
        return true;
      } catch (error) {
        const reasonRequired = isStaffReasonRequiredError(error);
        if (reasonRequired) {
          log.info('Staff reason required by server', {
            action: current.action,
            signupId: current.signupId,
          });
        }
        const updated = {
          ...current,
          required: current.required || reasonRequired,
          serverError: reasonRequired
            ? REQUIRED_MESSAGE
            : (extractApiError(error) ?? `Failed to ${current.errorLabel}`),
        };
        show(updated);
        return false;
      } finally {
        inFlight.current = false;
        setSubmitting(false);
      }
    },
  };

  return { run, dispatch, collect, dialogProps, isOpen: dialogProps.open };
}

export type StaffAction = ReturnType<typeof useStaffAction>;
