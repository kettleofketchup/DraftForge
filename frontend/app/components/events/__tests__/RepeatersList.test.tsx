// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { EventRepeaterListItem } from '~/components/api/api';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import { RepeatersList } from '../RepeatersList';

vi.mock('~/hooks/useEvent', () => ({
  useRepeaterSubscriptionMutation: () => ({
    subscribe: { isPending: false, mutate: vi.fn() },
    unsubscribe: { isPending: false, mutate: vi.fn() },
  }),
}));

const base: EventRepeaterListItem = {
  id: 7,
  organization: 1,
  organization_name: 'Org',
  name: 'Weekly Inhouse',
  frequency: 'weekly',
  day_of_week: 3,
  time_of_day: '19:00:00',
  timezone: 'America/New_York',
  is_active: true,
  discord_notify_new_events: true,
  subscriber_count: 2,
  is_subscribed: false,
  next_event_date: null,
};

function renderList(repeater: EventRepeaterListItem) {
  render(
    <MemoryRouter>
      <TooltipProvider>
        <RepeatersList repeaters={[repeater]} loading={false} />
      </TooltipProvider>
    </MemoryRouter>,
  );
}

describe('RepeatersList subscribe button', () => {
  beforeEach(() => {
    useUserStore.setState({
      currentUser: { pk: 5, username: 'viewer' } as UserType,
    });
  });

  it('offers Unsubscribe when the viewer is subscribed', () => {
    renderList({ ...base, is_subscribed: true });
    expect(screen.getByRole('button', { name: 'Unsubscribe' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Subscribe' })).toBeNull();
  });

  it('offers Subscribe when the viewer is not subscribed', () => {
    renderList(base);
    expect(screen.getByRole('button', { name: 'Subscribe' })).toBeTruthy();
  });

  it('hides the button when the series sends no new-event notices', () => {
    renderList({ ...base, discord_notify_new_events: false });
    expect(screen.queryByRole('button', { name: /subscribe/i })).toBeNull();
  });
});
