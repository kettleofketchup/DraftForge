// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { EventSignupRecordsConflict } from '~/components/api/eventsAPI';
import { TooltipProvider } from '~/components/ui/tooltip';
import { EventDeleteFlow } from '../EventDeleteFlow';
import type { EventType } from '../schemas';
import { event as fixture } from './eventModalFixtures';

const { success, error } = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: { success, error } }));

function setup(overrides: Partial<Parameters<typeof EventDeleteFlow>[0]> = {}) {
  const props = {
    event: { ...fixture, name: 'Community Night', signup_count: 8 },
    open: true,
    onOpenChange: vi.fn(),
    isOrganizationAdmin: true,
    isPending: false,
    onDelete: vi.fn().mockResolvedValue(undefined),
    onCancel: vi.fn().mockResolvedValue(undefined),
    onDeleted: vi.fn(),
    ...overrides,
  };
  function Harness() {
    const [open, setOpen] = useState(true);
    return (
      <TooltipProvider>
        <EventDeleteFlow
          {...props}
          open={open}
          onOpenChange={(value) => {
            setOpen(value);
            props.onOpenChange(value);
          }}
        />
      </TooltipProvider>
    );
  }
  const view = render(<Harness />);
  return { ...props, ...view };
}

async function warning(
  onDelete = vi.fn().mockRejectedValue(new EventSignupRecordsConflict(24)),
  admin = true,
) {
  const props = setup({ onDelete, isOrganizationAdmin: admin });
  fireEvent.click(screen.getByTestId('event-delete-initial-confirm'));
  await screen.findByTestId('event-delete-record-warning');
  return props;
}

beforeEach(() => vi.clearAllMocks());

describe('event deletion preservation', () => {
  it('explains the active count and starts with an unconfirmed request', async () => {
    const props = setup();
    expect(screen.getByText(/Active sign-ups: 8/)).toBeInTheDocument();
    expect(
      screen.getByText(/Historical signup records are retained/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('event-delete-initial-confirm'));
    await waitFor(() => expect(props.onDeleted).toHaveBeenCalledOnce());
    expect(props.onDelete).toHaveBeenCalledExactlyOnceWith();
  });

  it('shows a separate record stage with exact name confirmation for admins', async () => {
    const onDelete = vi
      .fn()
      .mockRejectedValueOnce(new EventSignupRecordsConflict(24))
      .mockResolvedValue(undefined);
    const props = await warning(onDelete);
    expect(screen.getByTestId('event-delete-record-count')).toHaveTextContent(
      '24',
    );
    const input = screen.getByTestId('event-delete-confirm-input');
    const confirm = screen.getByTestId('event-delete-record-confirm');
    expect(confirm).toBeDisabled();
    fireEvent.change(input, { target: { value: 'Community' } });
    expect(confirm).toBeDisabled();
    fireEvent.change(input, { target: { value: 'Community Night' } });
    fireEvent.click(confirm);
    await waitFor(() => expect(props.onDeleted).toHaveBeenCalledOnce());
    expect(onDelete.mock.calls).toEqual([[], [{ confirm: true }]]);
  });

  it('does not expose administrator override to organization staff', async () => {
    await warning(undefined, false);
    expect(
      screen.getByText(/Only an organization administrator/),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('event-delete-confirm-input')).toBeNull();
    expect(screen.queryByTestId('event-delete-record-confirm')).toBeNull();
  });

  it.each(['upcoming', 'signups_open', 'roll_call'] as const)(
    'offers cancellation in %s',
    (state) => {
      setup({ event: { ...fixture, state } });
      expect(
        screen.getByTestId('event-delete-cancel-instead'),
      ).toBeInTheDocument();
    },
  );

  it.each(['in_progress', 'completed', 'cancelled'] as const)(
    'never offers cancellation in %s',
    (state) => {
      setup({ event: { ...fixture, state } });
      expect(screen.queryByTestId('event-delete-cancel-instead')).toBeNull();
    },
  );

  it.each(['initial', 'unmatched', 'matched'] as const)(
    'Enter on cancellation in %s stage never sends DELETE',
    async (stage) => {
      const user = userEvent.setup();
      const props = stage === 'initial' ? setup() : await warning();
      if (stage === 'matched') {
        fireEvent.change(screen.getByTestId('event-delete-confirm-input'), {
          target: { value: 'Community Night' },
        });
        expect(screen.getByTestId('event-delete-record-confirm')).toBeEnabled();
      }
      vi.mocked(props.onDelete).mockClear();
      screen.getByTestId('event-delete-cancel-instead').focus();
      await user.keyboard('{Enter}');
      await waitFor(() => expect(props.onCancel).toHaveBeenCalledOnce());
      expect(props.onDelete).not.toHaveBeenCalled();
      expect(props.onDeleted).not.toHaveBeenCalled();
      expect(success).toHaveBeenCalledWith('Event cancelled');
    },
  );

  it('shows readable mutation errors and never navigates on failure', async () => {
    const props = setup({
      onDelete: vi.fn().mockRejectedValue({
        response: { status: 500, data: { detail: 'Deletion unavailable' } },
      }),
    });
    fireEvent.click(screen.getByTestId('event-delete-initial-confirm'));
    await waitFor(() =>
      expect(error).toHaveBeenCalledWith('Deletion unavailable'),
    );
    expect(props.onDeleted).not.toHaveBeenCalled();
  });

  it('does not navigate when confirmed authority is revoked', async () => {
    const onDelete = vi
      .fn()
      .mockRejectedValueOnce(new EventSignupRecordsConflict(24))
      .mockRejectedValue({ response: { status: 403 } });
    const props = await warning(onDelete);
    fireEvent.change(screen.getByTestId('event-delete-confirm-input'), {
      target: { value: 'Community Night' },
    });
    fireEvent.click(screen.getByTestId('event-delete-record-confirm'));
    await waitFor(() => expect(error).toHaveBeenCalled());
    expect(props.onDeleted).not.toHaveBeenCalled();
    expect(onDelete).toHaveBeenCalledTimes(2);
    expect(screen.queryByTestId('event-delete-record-confirm')).toBeNull();
  });

  it('keeps a failed cancellation in the flow and does not delete', async () => {
    const props = setup({
      onCancel: vi.fn().mockRejectedValue(new Error('failed')),
    });
    fireEvent.click(screen.getByTestId('event-delete-cancel-instead'));
    await waitFor(() => expect(error).toHaveBeenCalled());
    expect(props.onDelete).not.toHaveBeenCalled();
    expect(props.onDeleted).not.toHaveBeenCalled();
    expect(
      screen.getByTestId('event-delete-initial-confirm'),
    ).toBeInTheDocument();
  });

  it('disables confirmation and cancellation during a pending mutation', () => {
    setup({ isPending: true });
    expect(screen.getByTestId('event-delete-initial-confirm')).toBeDisabled();
    expect(screen.getByTestId('event-delete-cancel-instead')).toBeDisabled();
  });

  it('resets the warning and typed name when the event changes', async () => {
    const props = await warning();
    fireEvent.change(screen.getByTestId('event-delete-confirm-input'), {
      target: { value: 'Community Night' },
    });
    props.rerender(
      <TooltipProvider>
        <EventDeleteFlow
          {...props}
          event={{ ...props.event, id: 52 } as EventType}
        />
      </TooltipProvider>,
    );
    expect(screen.queryByTestId('event-delete-confirm-input')).toBeNull();
    expect(
      screen.getByTestId('event-delete-initial-confirm'),
    ).toBeInTheDocument();
  });
});

it('blocks a second delete and cancellation while the first delete is unresolved', async () => {
  let resolve!: () => void;
  const pending = new Promise<void>((done) => {
    resolve = done;
  });
  const onDelete = vi.fn().mockReturnValue(pending);
  const props = setup({ onDelete });
  const confirm = screen.getByTestId('event-delete-initial-confirm');
  fireEvent.click(confirm);
  fireEvent.click(confirm);
  fireEvent.click(screen.getByTestId('event-delete-cancel-instead'));
  expect(onDelete).toHaveBeenCalledOnce();
  expect(props.onCancel).not.toHaveBeenCalled();
  resolve();
  await waitFor(() => expect(props.onDeleted).toHaveBeenCalledOnce());
});

it('ignores a previous event deletion result after navigation to another event', async () => {
  let resolve!: () => void;
  const pending = new Promise<void>((done) => {
    resolve = done;
  });
  const props = setup({ onDelete: vi.fn().mockReturnValue(pending) });
  fireEvent.click(screen.getByTestId('event-delete-initial-confirm'));
  props.rerender(
    <TooltipProvider>
      <EventDeleteFlow {...props} event={{ ...props.event, id: 52 }} />
    </TooltipProvider>,
  );
  resolve();
  await waitFor(() =>
    expect(screen.getByTestId('event-delete-initial-confirm')).toBeEnabled(),
  );
  expect(props.onDeleted).not.toHaveBeenCalled();
});
