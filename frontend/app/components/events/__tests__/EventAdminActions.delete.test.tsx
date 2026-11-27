// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { EventSignupRecordsConflict } from '~/components/api/eventsAPI';
import { TooltipProvider } from '~/components/ui/tooltip';
import { EventAdminActions } from '../EventAdminActions';
import type { EventType } from '../schemas';
import { event as fixture } from './eventModalFixtures';

function idle() {
  return { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
}

const actions = {
  openSignups: idle(),
  startRollCall: idle(),
  reopenSignups: idle(),
  cancelEvent: idle(),
  deleteEvent: idle(),
  completeEvent: idle(),
} as unknown as Parameters<typeof EventAdminActions>[0]['actions'];

function renderActions(
  overrides: Partial<Parameters<typeof EventAdminActions>[0]> = {},
) {
  const props = {
    event: { ...fixture, state: 'signups_open' } as EventType,
    actions,
    canComplete: false,
    canDelete: true,
    isOrganizationAdmin: false,
    onEditClick: vi.fn(),
    onStartRollCallClick: vi.fn(),
    onReopenSignupsClick: vi.fn(),
    onOpenRollCallClick: vi.fn(),
    onDelete: vi.fn().mockRejectedValue(new EventSignupRecordsConflict(3)),
    onCancel: vi.fn().mockResolvedValue(undefined),
    onDeleted: vi.fn(),
    onCompleteConfirmed: vi.fn(),
    ...overrides,
  };
  render(
    <TooltipProvider>
      <EventAdminActions {...props} />
    </TooltipProvider>,
  );
  return props;
}

describe('EventAdminActions deletion', () => {
  it('opens the shared preservation flow from the desktop delete button', async () => {
    const props = renderActions();
    fireEvent.click(screen.getByTestId('event-delete-btn'));
    fireEvent.click(await screen.findByTestId('event-delete-initial-confirm'));
    await screen.findByTestId('event-delete-record-warning');
    expect(props.onDelete).toHaveBeenCalledExactlyOnceWith();
    expect(props.onDeleted).not.toHaveBeenCalled();
  });

  it('opens the same flow from the mobile menu without duplicating desktop ids', async () => {
    renderActions();
    const mobile = screen.getByTestId('event-admin-actions-mobile');
    fireEvent.pointerDown(mobile, {
      button: 0,
      ctrlKey: false,
    });
    fireEvent.click(await screen.findByTestId('event-mobile-delete'));
    expect(
      await screen.findByTestId('event-delete-initial-confirm'),
    ).toBeInTheDocument();
    expect(screen.getAllByTestId('event-delete-btn')).toHaveLength(1);
  });

  it('hides deletion from league-only managers', () => {
    renderActions({ canDelete: false });
    expect(screen.queryByTestId('event-delete-btn')).toBeNull();
  });

  it('hides cancellation for in-progress events', () => {
    renderActions({ event: { ...fixture, state: 'in_progress' } as EventType });
    expect(screen.queryByTestId('event-cancel-btn')).toBeNull();
  });

  it('keeps cancellation through roll call', async () => {
    renderActions({ event: { ...fixture, state: 'roll_call' } as EventType });
    expect(screen.getByTestId('event-cancel-btn')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
  });
});
