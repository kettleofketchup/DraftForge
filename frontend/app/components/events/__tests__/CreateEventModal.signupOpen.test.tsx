// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { orgDefaults, submit, Wrapper } from './eventModalFixtures';

const api = vi.hoisted(() => ({
  createEvent: vi.fn(),
  createEventRepeater: vi.fn(),
  getOrgEventDefaults: vi.fn(),
  mutateAsync: vi.fn(),
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  createEvent: api.createEvent,
  createEventRepeater: api.createEventRepeater,
  getOrgEventDefaults: api.getOrgEventDefaults,
  fetchCurrentUser: vi.fn().mockResolvedValue({}),
  getDiscordChannels: vi.fn().mockResolvedValue([]),
  getDiscordRoles: vi.fn().mockResolvedValue([]),
  getLeagues: vi.fn().mockResolvedValue([]),
}));

vi.mock('~/hooks/useEvent', () => ({
  useUpdateOrgDefaultsMutation: () => ({
    mutateAsync: api.mutateAsync,
    isPending: false,
  }),
}));

vi.mock('~/components/league/LeagueCombobox', () => ({
  LeagueCombobox: () => null,
}));

// Heavy fields these tests never use; rendering them timed tests out under load.
vi.mock('../form/sections/EventTournamentFields', () => ({
  EventTournamentFields: () => null,
}));
vi.mock('../form/sections/EventLobbyFields', () => ({
  EventLobbyFields: () => null,
}));
vi.mock('../form/fields/TimezoneField', () => ({ TimezoneField: () => null }));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

import { CreateEventModal } from '../CreateEventModal';
import { OrgEventDefaultsHarness } from './orgEventDefaultsHarness';

const {
  signup_open_mode: _m,
  signups_open_hours_before: _h,
  ...legacyDefaults
} = orgDefaults;

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.createEvent.mockResolvedValue({ id: 99 });
  api.createEventRepeater.mockResolvedValue({ id: 98 });
  api.mutateAsync.mockResolvedValue({});
  api.getOrgEventDefaults.mockResolvedValue(orgDefaults);
});

async function renderReady() {
  render(<CreateEventModal open onOpenChange={() => {}} organizationId={1} />, {
    wrapper: Wrapper,
  });
  fireEvent.change(await screen.findByTestId('event-name-input'), {
    target: { value: 'Night 5' },
  });
}

function chooseDays(days: string) {
  fireEvent.click(screen.getByTestId('signup-open-mode-scheduled'));
  fireEvent.change(screen.getByTestId('signup-open-days-input'), {
    target: { value: days },
  });
}

describe('CreateEventModal signup open policy', () => {
  it('sends the scheduled policy for a single event without computing the open time', async () => {
    await renderReady();
    chooseDays('2');
    submit();
    await waitFor(() => expect(api.createEvent).toHaveBeenCalled());
    const [body, openNow] = api.createEvent.mock.calls[0];
    expect(body).toMatchObject({
      signup_open_mode: 'scheduled',
      signups_open_hours_before: 48,
    });
    expect(body).not.toHaveProperty('signups_open_at');
    expect(openNow).toBe(false);
  });

  it('opens a single event at once when immediate is chosen', async () => {
    await renderReady();
    fireEvent.click(screen.getByTestId('signup-open-mode-immediate'));
    submit();
    await waitFor(() => expect(api.createEvent).toHaveBeenCalled());
    const [body, openNow] = api.createEvent.mock.calls[0];
    expect(body).toMatchObject({ signup_open_mode: 'immediate' });
    expect(openNow).toBe(true);
  });

  it('renders the section for a recurring event and sends the policy to the series', async () => {
    await renderReady();
    fireEvent.click(screen.getByTestId('event-recurring-checkbox'));
    chooseDays('2');
    submit();
    await waitFor(() => expect(api.createEventRepeater).toHaveBeenCalled());
    expect(api.createEventRepeater.mock.calls[0][0]).toMatchObject({
      signup_open_mode: 'scheduled',
      signups_open_hours_before: 48,
    });
  });

  it('falls back to manual and 72 hours when org defaults carry no policy', async () => {
    api.getOrgEventDefaults.mockResolvedValue(legacyDefaults);
    await renderReady();
    fireEvent.click(screen.getByTestId('event-recurring-checkbox'));
    submit();
    await waitFor(() => expect(api.createEventRepeater).toHaveBeenCalled());
    expect(api.createEventRepeater.mock.calls[0][0]).toMatchObject({
      signup_open_mode: 'manual',
      signups_open_hours_before: 72,
    });
  });

  it('starts at manual when there are no org defaults', async () => {
    api.getOrgEventDefaults.mockResolvedValue(null);
    render(
      <CreateEventModal open onOpenChange={() => {}} organizationId={1} />,
      { wrapper: Wrapper },
    );
    expect(await screen.findByTestId('signup-open-mode-manual')).toBeChecked();
  });

  it('sends the org default policy for an untouched recurring create', async () => {
    api.getOrgEventDefaults.mockResolvedValue({
      ...orgDefaults,
      signup_open_mode: 'scheduled',
      signups_open_hours_before: 48,
    });
    await renderReady();
    fireEvent.click(screen.getByTestId('event-recurring-checkbox'));
    expect(screen.getByTestId('signup-open-days-input')).toHaveValue(2);
    submit();
    await waitFor(() => expect(api.createEventRepeater).toHaveBeenCalled());
    expect(api.createEventRepeater.mock.calls[0][0]).toMatchObject({
      signup_open_mode: 'scheduled',
      signups_open_hours_before: 48,
    });
  });

  it('never renders the signup deadline', async () => {
    await renderReady();
    chooseDays('2');
    expect(screen.queryByText(/deadline/i)).toBeNull();
  });
});

describe('org event defaults signup open policy', () => {
  it('round-trips the stored policy and sends edits', async () => {
    api.getOrgEventDefaults.mockResolvedValue({
      ...orgDefaults,
      signup_open_mode: 'scheduled',
      signups_open_hours_before: 72,
    });
    render(<OrgEventDefaultsHarness organizationId={1} />, {
      wrapper: Wrapper,
    });
    expect(
      await screen.findByTestId('org-defaults-max-players-input'),
    ).toHaveValue(orgDefaults.max_players);
    expect(screen.getByTestId('signup-open-days-input')).toHaveValue(3);
    fireEvent.change(screen.getByTestId('signup-open-days-input'), {
      target: { value: '5' },
    });
    submit();
    await waitFor(() => expect(api.mutateAsync).toHaveBeenCalled());
    expect(api.mutateAsync.mock.calls[0][0]).toMatchObject({
      id: orgDefaults.id,
      data: { signup_open_mode: 'scheduled', signups_open_hours_before: 120 },
    });
  });
});
