import { toast } from 'sonner';
import { getLogger } from '~/lib/logger';
import { describeTimerActionError } from '../pickErrors';

const log = getLogger('runTimerAction');

export interface TimerActionProgress {
  loading: string;
  success: string;
}

/** Runs a timer action, toasts its failure once, and never rejects. */
export async function runTimerAction<T>(
  action: () => Promise<T>,
  fallback: string,
  progress?: TimerActionProgress,
): Promise<T | undefined> {
  const promise = (async () => action())();
  if (progress) {
    toast.promise(promise, { ...progress, error: (err: unknown) => describeTimerActionError(err, fallback) });
  }
  try {
    return await promise;
  } catch (err) {
    log.error(fallback, err);
    if (!progress) toast.error(describeTimerActionError(err, fallback));
    return undefined;
  }
}
