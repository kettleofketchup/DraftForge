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
  const [submitting, setSubmitting] = useState(false);
  const inFlight = useRef(false);

  useEffect(
    () => () => {
      active.current?.resolve(null);
      active.current = null;
    },
    [],
  );

  const finish = (reason: string | null) => {
    const current = active.current;
    active.current = null;
    setPrompt(null);
    current?.resolve(reason);
  };

  const ask = (options: Omit<Prompt, 'resolve'>): Promise<string | null> => {
    if (active.current) return Promise.resolve(null);
    return new Promise((resolve) => {
      const next = { ...options, resolve };
      active.current = next;
      setPrompt(next);
    });
  };

  const run = async (
    action: StaffSignupAction,
    signup: Signup,
    fire: Fire,
    opts: ActionOptions = {},
  ): Promise<boolean> => {
    if (active.current) return false;
    const required =
      staffReasonMode(policy, action, {
        fromStatus: signup.status,
        isSelf: signup.user === currentUserId,
      }) === 'required';
    const options = {
      action,
      signupId: signup.id,
      title: opts.title ?? 'Change signup',
      actionLabel: opts.actionLabel ?? 'Confirm',
      errorLabel: opts.errorLabel ?? action.replaceAll('_', ' '),
      required,
      initialReason: opts.reason ?? '',
      fire,
    };
    if (required && !opts.reason?.trim()) return (await ask(options)) !== null;
    try {
      await fire(opts.reason);
      return true;
    } catch (error) {
      if (isStaffReasonRequiredError(error)) {
        log.info('Staff reason required by server', {
          action,
          signupId: signup.id,
        });
        return (
          (await ask({
            ...options,
            required: true,
            serverError: REQUIRED_MESSAGE,
          })) !== null
        );
      }
      toast.error(extractApiError(error) ?? `Failed to ${options.errorLabel}`);
      return false;
    }
  };

  const collect = (
    action: StaffSignupAction,
    target: { userId: number; title?: string },
  ): Promise<string | null> =>
    ask({
      action,
      title: target.title ?? 'Change signup',
      actionLabel: 'Confirm',
      errorLabel: action.replaceAll('_', ' '),
      required:
        staffReasonMode(policy, action, {
          isSelf: target.userId === currentUserId,
        }) === 'required',
      initialReason: '',
    });

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
    onOpenChange: (open) => {
      if (!open && !inFlight.current) finish(null);
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
        active.current = updated;
        setPrompt(updated);
        return false;
      } finally {
        inFlight.current = false;
        setSubmitting(false);
      }
    },
  };

  return { run, collect, dialogProps, isOpen: dialogProps.open };
}
