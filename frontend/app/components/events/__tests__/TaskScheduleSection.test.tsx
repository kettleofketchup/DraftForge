// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { toast } from 'sonner';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import api from '~/components/api/axios';
import { TooltipProvider } from '~/components/ui/tooltip';
import {
  fireConfirmDescription,
  TaskScheduleSection,
  type TaskEntry,
} from '../TaskScheduleSection';

vi.mock('~/components/api/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}));
vi.mock('~/store/userStore', () => ({
  useUserStore: (selector: (state: { currentUser: null }) => unknown) =>
    selector({ currentUser: null }),
}));

const warning = 'This queues a fresh post. An earlier post may already exist.';

// Matches the real schedule response after an uncertain first delivery.
const uncertainSignup: TaskEntry = {
  task: 'signup_post',
  label: 'Signup Post',
  fires_at: null,
  description: 'Creates forum thread or message for signups',
  check_interval: 'On signups open',
  last_fired_at: null,
  fired_by: null,
  can_fire: true,
  status: 'ready',
};

function renderSchedule(task: TaskEntry = uncertainSignup) {
  vi.mocked(api.get).mockResolvedValue({ data: [task] });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <TaskScheduleSection eventId={42} isAdmin />
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

async function openConfirmation(taskName = 'signup_post') {
  fireEvent.click(await screen.findByTestId(`fire-task-${taskName}`));
  return screen.findByRole('alertdialog');
}

async function confirmSignup() {
  renderSchedule();
  await openConfirmation();
  expect(api.post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Queue repost' }));
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.post).mockResolvedValue({
    data: { fired: true, event_id: 42 },
  });
});
afterEach(cleanup);

describe('signup post confirmation', () => {
  for (const task of ['signup_post', 'announcement']) {
    for (const status of [
      'ready',
      'pending',
      'fired',
      'disabled',
      'misconfigured',
    ] as const) {
      it(`warns ${task} in ${status} may duplicate and labels the action Queue repost`, async () => {
        const entry = { ...uncertainSignup, task, status };
        expect(fireConfirmDescription(entry)).toContain(warning);
        renderSchedule(entry);
        await openConfirmation(task);
        expect(screen.getByRole('alertdialog').textContent).toContain(warning);
        expect(
          screen.getByRole('button', { name: 'Queue repost' }),
        ).toBeTruthy();
        expect(api.post).not.toHaveBeenCalled();
      });
    }
  }

  it('uncertain first delivery without success logs still warns before request', async () => {
    renderSchedule();
    expect(
      (await screen.findByTestId('task-schedule-entry-signup_post'))
        .textContent,
    ).toContain('Ready');
    expect(api.post).not.toHaveBeenCalled();
    await openConfirmation();
    expect(screen.getByRole('alertdialog').textContent).toContain(warning);
    expect(api.post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(api.post).not.toHaveBeenCalled();
    await openConfirmation();
    fireEvent.click(screen.getByRole('button', { name: 'Queue repost' }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledExactlyOnceWith(
        '/events/42/task-schedule/signup_post/fire/',
      ),
    );
  });

  it('success toast says queued', async () => {
    await confirmSignup();
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('Task "signup_post" queued'),
    );
  });

  it('409 shows the in-progress warning unchanged', async () => {
    const message =
      'A signup post attempt is already in progress. Try again after it finishes.';
    vi.mocked(api.post).mockRejectedValue({
      response: { status: 409, data: { error: message } },
    });
    await confirmSignup();
    await waitFor(() => expect(toast.warning).toHaveBeenCalledWith(message));
    expect(toast.error).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('503 shows failed to queue with the backend detail', async () => {
    const message =
      'Could not queue the signup post. Automatic posting will retry.';
    vi.mocked(api.post).mockRejectedValue({
      response: { status: 503, data: { error: message } },
    });
    await confirmSignup();
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        `Failed to queue "signup_post": ${message}`,
      ),
    );
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('preserves the start-mention warning and confirmation label', async () => {
    renderSchedule({
      ...uncertainSignup,
      task: 'start_mention',
      label: 'Start Mention',
    });
    await openConfirmation('start_mention');
    expect(screen.getByRole('alertdialog').textContent).toContain(
      '@mention every signed-up member',
    );
    expect(screen.getByRole('button', { name: 'Fire Now' })).toBeTruthy();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('preserves generic task confirmation text', async () => {
    renderSchedule({
      ...uncertainSignup,
      task: 'profile_reminder',
      label: 'Profile Reminder',
    });
    await openConfirmation('profile_reminder');
    expect(screen.getByRole('alertdialog').textContent).toContain(
      'This will immediately execute "Profile Reminder" for this event. This action cannot be undone.',
    );
    expect(screen.getByRole('button', { name: 'Fire Now' })).toBeTruthy();
    expect(api.post).not.toHaveBeenCalled();
  });
});
