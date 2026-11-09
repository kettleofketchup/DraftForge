import { toast } from 'sonner';
import { getLogger } from '~/lib/logger';
import { describeTimerActionError } from '../pickErrors';

const log = getLogger('runTimerAction');

export async function runTimerAction(action: () => Promise<unknown>, fallback: string): Promise<void> {
  try {
    await action();
  } catch (err) {
    log.error(fallback, err);
    toast.error(describeTimerActionError(err, fallback));
  }
}
