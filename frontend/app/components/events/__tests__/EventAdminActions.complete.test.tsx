// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { EventAdminActions } from '../EventAdminActions';
import type { EventType } from '../schemas';

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

const event = { id: 11, name: 'Night 4', state: 'in_progress' } as unknown as EventType;

function renderActions(
  canComplete: boolean,
  onCompleteConfirmed = vi.fn(),
  showCompletePointsNote = false,
) {
  render(
    <TooltipProvider>
      <EventAdminActions
        event={event}
        actions={actions}
        canComplete={canComplete}
        showCompletePointsNote={showCompletePointsNote}
        onEditClick={vi.fn()}
        onStartRollCallClick={vi.fn()}
        onReopenSignupsClick={vi.fn()}
        onOpenRollCallClick={vi.fn()}
        onDeleteConfirmed={vi.fn()}
        onCompleteConfirmed={onCompleteConfirmed}
      />
    </TooltipProvider>,
  );
  return onCompleteConfirmed;
}

describe('EventAdminActions complete', () => {
  it('hides the Complete button when the viewer cannot complete', () => {
    renderActions(false);
    expect(screen.queryByTestId('event-complete-btn')).toBeNull();
  });

  it('confirms before completing', async () => {
    const onCompleteConfirmed = renderActions(true);
    fireEvent.click(screen.getByTestId('event-complete-btn'));
    expect(onCompleteConfirmed).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByTestId('event-complete-dialog-confirm'));
    await waitFor(() => expect(onCompleteConfirmed).toHaveBeenCalled());
  });

  it('leaves points out of the confirm text when contributions are hidden', async () => {
    renderActions(true);
    fireEvent.click(screen.getByTestId('event-complete-btn'));
    await screen.findByTestId('event-complete-dialog-confirm');
    expect(document.body.textContent).not.toMatch(/points/i);
  });

  it('mentions host and helper points when contributions are visible', async () => {
    renderActions(true, vi.fn(), true);
    fireEvent.click(screen.getByTestId('event-complete-btn'));
    await screen.findByTestId('event-complete-dialog-confirm');
    expect(document.body.textContent).toMatch(/helper points are awarded/i);
  });
});
