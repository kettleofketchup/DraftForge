// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  event,
  openTab,
  orgDefaults,
  repeater,
  submit,
  Wrapper,
} from './eventModalFixtures';

// Every write seam the five modals use; the body is the assertion target.
const api = vi.hoisted(() => ({
  createEvent: vi.fn(),
  createEventRepeater: vi.fn(),
  createSeriesOneOffEvent: vi.fn(),
  getOrgEventDefaults: vi.fn(),
  mutateAsync: vi.fn(),
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  createEvent: api.createEvent,
  createEventRepeater: api.createEventRepeater,
  createSeriesOneOffEvent: api.createSeriesOneOffEvent,
  getOrgEventDefaults: api.getOrgEventDefaults,
  fetchCurrentUser: vi.fn().mockResolvedValue({}),
  getDiscordChannels: vi.fn().mockResolvedValue([]),
  getDiscordRoles: vi.fn().mockResolvedValue([]),
  getLeagues: vi.fn().mockResolvedValue([]),
}));

vi.mock('~/hooks/useEvent', () => ({
  useUpdateEventMutation: () => ({
    mutateAsync: api.mutateAsync,
    isPending: false,
  }),
  useUpdateEventRepeaterMutation: () => ({
    mutateAsync: api.mutateAsync,
    isPending: false,
  }),
  useUpdateOrgDefaultsMutation: () => ({
    mutateAsync: api.mutateAsync,
    isPending: false,
  }),
}));

vi.mock('~/hooks/useLobbyPassword', () => ({
  useEventLobbyPassword: () => ({ data: undefined }),
  useRepeaterLobbyPassword: () => ({ data: undefined }),
  useRegenerateEventLobbyPassword: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
}));

vi.mock('~/components/league/LeagueCombobox', () => ({
  LeagueCombobox: () => null,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

import { CreateEventModal } from '../CreateEventModal';
import { CreateSeriesEventModal } from '../CreateSeriesEventModal';
import { EditEventModal } from '../EditEventModal';
import { EditOrgDefaultsModal } from '../EditOrgDefaultsModal';
import { EditRepeaterModal } from '../EditRepeaterModal';

const ROSTER_LABEL = 'Players join the roster only after confirming';
const SELF_SERVE_LABEL = 'Members can sign themselves up';

async function toggleRules() {
  fireEvent.click(await screen.findByLabelText(ROSTER_LABEL));
  fireEvent.click(screen.getByLabelText(SELF_SERVE_LABEL));
}

const TOGGLED = { roll_call_enabled: true, allow_user_signups: false };

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.createEvent.mockResolvedValue({ id: 99 });
  api.createEventRepeater.mockResolvedValue({ id: 98 });
  api.createSeriesOneOffEvent.mockResolvedValue({ id: 97 });
  api.mutateAsync.mockResolvedValue({});
  api.getOrgEventDefaults.mockResolvedValue(orgDefaults);
});

describe('CreateEventModal signup rules', () => {
  async function renderReady() {
    render(
      <CreateEventModal open onOpenChange={() => {}} organizationId={1} />,
      { wrapper: Wrapper },
    );
    fireEvent.change(await screen.findByTestId('event-name-input'), {
      target: { value: 'Night 5' },
    });
  }

  it('starts from the org defaults', async () => {
    api.getOrgEventDefaults.mockResolvedValue({
      ...orgDefaults,
      roll_call_enabled: true,
      allow_user_signups: false,
    });
    await renderReady();
    openTab(/approval/i);
    expect(await screen.findByLabelText(ROSTER_LABEL)).toBeChecked();
    expect(screen.getByLabelText(SELF_SERVE_LABEL)).not.toBeChecked();
  });

  it('sends both flags for a single event', async () => {
    await renderReady();
    openTab(/approval/i);
    await toggleRules();
    submit();
    await waitFor(() => expect(api.createEvent).toHaveBeenCalled());
    expect(api.createEvent.mock.calls[0][0]).toMatchObject(TOGGLED);
  });

  it('sends both flags for a recurring series', async () => {
    await renderReady();
    fireEvent.click(screen.getByTestId('event-recurring-checkbox'));
    openTab(/approval/i);
    await toggleRules();
    submit();
    await waitFor(() => expect(api.createEventRepeater).toHaveBeenCalled());
    expect(api.createEventRepeater.mock.calls[0][0]).toMatchObject(TOGGLED);
  });
});

describe('CreateSeriesEventModal signup rules', () => {
  it("starts from the series' flags and sends the toggled values", async () => {
    render(
      <CreateSeriesEventModal
        repeater={{ ...repeater, allow_user_signups: false }}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: Wrapper },
    );
    fireEvent.change(screen.getByTestId('one-off-scheduled-input'), {
      target: { value: '2026-09-30T20:00' },
    });
    openTab(/approval/i);
    expect(await screen.findByLabelText(SELF_SERVE_LABEL)).not.toBeChecked();
    fireEvent.click(screen.getByLabelText(ROSTER_LABEL));
    submit();
    await waitFor(() => expect(api.createSeriesOneOffEvent).toHaveBeenCalled());
    expect(api.createSeriesOneOffEvent.mock.calls[0][1]).toMatchObject(TOGGLED);
  });
});

describe('EditEventModal signup rules', () => {
  it("starts from the event's flags", async () => {
    render(
      <EditEventModal
        event={{ ...event, roll_call_enabled: true }}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: Wrapper },
    );
    openTab(/approval/i);
    expect(await screen.findByLabelText(ROSTER_LABEL)).toBeChecked();
    expect(screen.getByLabelText(SELF_SERVE_LABEL)).toBeChecked();
  });

  it('sends the toggled flags', async () => {
    render(<EditEventModal event={event} open onOpenChange={() => {}} />, {
      wrapper: Wrapper,
    });
    openTab(/approval/i);
    await toggleRules();
    submit();
    await waitFor(() => expect(api.mutateAsync).toHaveBeenCalled());
    expect(api.mutateAsync.mock.calls[0][0]).toMatchObject(TOGGLED);
  });
});

describe('EditRepeaterModal signup rules', () => {
  it('sends the toggled flags', async () => {
    render(
      <EditRepeaterModal repeater={repeater} open onOpenChange={() => {}} />,
      { wrapper: Wrapper },
    );
    await toggleRules();
    submit();
    await waitFor(() => expect(api.mutateAsync).toHaveBeenCalled());
    expect(api.mutateAsync.mock.calls[0][0]).toMatchObject(TOGGLED);
  });
});

describe('EditOrgDefaultsModal signup rules', () => {
  it('sends the toggled flags', async () => {
    render(
      <EditOrgDefaultsModal organizationId={1} open onOpenChange={() => {}} />,
      { wrapper: Wrapper },
    );
    await waitFor(() => expect(api.getOrgEventDefaults).toHaveBeenCalled());
    await screen.findByDisplayValue('Night Cup');
    await toggleRules();
    submit();
    await waitFor(() => expect(api.mutateAsync).toHaveBeenCalled());
    expect(api.mutateAsync.mock.calls[0][0]).toMatchObject({
      id: orgDefaults.id,
      data: TOGGLED,
    });
  });
});
