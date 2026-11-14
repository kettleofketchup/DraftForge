// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OrgFeatureAccess } from '~/features/org-features';
import { getPointValues } from '~/features/contributions/api';
import type { EventType } from '../schemas';

const mutateAsync = vi.hoisted(() => vi.fn());
vi.mock('~/hooks/useEvent', () => ({
  useEventActionMutation: () => ({ setEventStaff: { mutateAsync, isPending: false } }),
}));

vi.mock('~/features/contributions/api', () => ({
  getPointValues: vi.fn().mockResolvedValue([
    { kind: 'promo_message', points: 1, default: 1, is_default: true },
    { kind: 'event_host', points: 12, default: 10, is_default: false },
    { kind: 'event_helper', points: 5, default: 5, is_default: true },
  ]),
}));

vi.mock('~/components/user/AddUserModal', () => ({
  AddUserModal: ({
    open,
    onAdd,
  }: {
    open: boolean;
    onAdd: (payload: { user_id: number }) => Promise<unknown>;
  }) =>
    open ? (
      <div>
        <button type="button" data-testid="stub-pick-2" onClick={() => void onAdd({ user_id: 2 })}>
          pick 2
        </button>
        <button type="button" data-testid="stub-pick-9" onClick={() => void onAdd({ user_id: 9 })}>
          pick 9
        </button>
      </div>
    ) : null,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

import { EventStaffCard, EventStaffSection } from '../EventStaffCard';

const alice = { pk: 2, username: 'alice', nickname: null, avatarUrl: null };
const bob = { pk: 3, username: 'bob', nickname: 'Bobby', avatarUrl: null };
const carol = { pk: 4, username: 'carol', nickname: null, avatarUrl: null };

const event = {
  id: 11,
  organization: 1,
  name: 'Night 4',
  state: 'in_progress',
  host: carol,
  helpers: [alice, bob],
  user_can_manage_event_staff: true,
} as unknown as EventType;

const access: OrgFeatureAccess = {
  settled: true,
  viewerPk: 5,
  canUsePromotion: false,
  canManageTemplates: false,
  canManagePromoters: false,
  canViewContributions: true,
  canViewContributors: true,
  canManageContributions: false,
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  mutateAsync.mockReset();
  mutateAsync.mockResolvedValue(event);
  vi.mocked(getPointValues).mockClear();
});

describe('EventStaffCard', () => {
  it('moves a helper picked as host out of the helpers in the saved payload', async () => {
    render(<EventStaffCard event={event} canEdit showPoints={false} />, { wrapper });

    fireEvent.click(screen.getByTestId('event-host-edit-btn'));
    fireEvent.click(await screen.findByTestId('stub-pick-2'));

    await waitFor(() => expect(screen.queryByTestId('event-helper-remove-2')).toBeNull());
    expect(screen.getByTestId('event-helper-remove-3')).toBeTruthy();

    fireEvent.click(screen.getByTestId('event-staff-save-btn'));
    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({ host_id: 2, helper_ids: [3] }),
    );
  });

  it('adds a helper and removes one before saving', async () => {
    render(<EventStaffCard event={event} canEdit showPoints={false} />, { wrapper });

    fireEvent.click(screen.getByTestId('event-helper-add-btn'));
    fireEvent.click(await screen.findByTestId('stub-pick-9'));
    fireEvent.click(screen.getByTestId('event-helper-remove-2'));

    fireEvent.click(screen.getByTestId('event-staff-save-btn'));
    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({ host_id: 4, helper_ids: [3, 9] }),
    );
  });

  it('shows no editing controls when the viewer cannot edit', () => {
    render(<EventStaffCard event={event} canEdit={false} showPoints={false} />, { wrapper });

    expect(screen.getByTestId('event-staff-card').textContent).toContain('carol');
    expect(screen.queryByTestId('event-host-edit-btn')).toBeNull();
    expect(screen.queryByTestId('event-helper-add-btn')).toBeNull();
    expect(screen.queryByTestId('event-staff-save-btn')).toBeNull();
  });

  it('shows no points text when showPoints is false', () => {
    render(
      <EventStaffCard
        event={event}
        canEdit
        showPoints={false}
        pointValues={{ event_host: 12, event_helper: 5 }}
      />,
      { wrapper },
    );

    expect(screen.getByTestId('event-staff-card').textContent).not.toMatch(/pts|points/i);
  });

  it('shows the configured per-kind points when showPoints is true', () => {
    render(
      <EventStaffCard
        event={event}
        canEdit
        showPoints
        pointValues={{ event_host: 12, event_helper: 5 }}
      />,
      { wrapper },
    );

    const text = screen.getByTestId('event-staff-card').textContent ?? '';
    expect(text).toContain('+12 pts');
    expect(text).toContain('+5 pts');
  });
});

describe('EventStaffSection', () => {
  it('makes no point-values request when the viewer cannot manage contributions', async () => {
    render(<EventStaffSection event={event} access={access} hasDiscordServer={false} />, {
      wrapper,
    });

    expect(screen.getByTestId('event-staff-card')).toBeTruthy();
    await new Promise((r) => setTimeout(r, 0));
    expect(getPointValues).not.toHaveBeenCalled();
    expect(screen.getByTestId('event-staff-card').textContent).not.toMatch(/pts|points/i);
  });

  it('fetches point values and shows them to contributions managers', async () => {
    render(
      <EventStaffSection
        event={event}
        access={{ ...access, canManageContributions: true }}
        hasDiscordServer={false}
      />,
      { wrapper },
    );

    await waitFor(() =>
      expect(screen.getByTestId('event-staff-card').textContent).toContain('+12 pts'),
    );
    expect(getPointValues).toHaveBeenCalledWith(1);
  });
});
