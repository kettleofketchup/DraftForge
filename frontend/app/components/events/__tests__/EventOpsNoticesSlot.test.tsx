// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { OpsNotice } from '~/components/api/opsNoticesAPI';

const { fetchEventOpsNotices, resolveEventOpsNotice } = vi.hoisted(() => ({
  fetchEventOpsNotices: vi.fn(),
  resolveEventOpsNotice: vi.fn(),
}));

vi.mock('~/components/api/opsNoticesAPI', () => ({
  fetchEventOpsNotices,
  resolveEventOpsNotice,
}));

import { EventOpsNoticesSlot } from '../EventOpsNoticesSlot';

const notice: OpsNotice = {
  id: 1,
  key: 'test.alert',
  label: 'Test alert',
  category: 'urgent',
  severity: 'critical',
  state: 'open',
  summary: 'Lobby bot is offline',
  event_id: 11,
  event_name: 'Night 4',
  subject_user: null,
  actor: null,
  dedupe_key: '',
  occurrences: 1,
  first_seen_at: new Date().toISOString(),
  last_seen_at: new Date().toISOString(),
  closed_at: null,
  close_note: '',
  delivery_state: 'pending',
  payload: {},
};

function renderSlot(flags: {
  user_can_manage: boolean;
  user_is_event_operator: boolean;
}): HTMLElement {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
  return render(<EventOpsNoticesSlot event={{ id: 11, ...flags }} />, {
    wrapper,
  }).container;
}

beforeEach(() => {
  fetchEventOpsNotices.mockReset();
  fetchEventOpsNotices.mockResolvedValue([notice]);
});

afterEach(cleanup);

describe('EventOpsNoticesSlot', () => {
  it('shows the card to an operator who cannot manage the event', async () => {
    renderSlot({ user_can_manage: false, user_is_event_operator: true });
    expect(await screen.findByTestId('ops-notices-card')).toBeInTheDocument();
    expect(fetchEventOpsNotices).toHaveBeenCalledWith(11, expect.anything());
  });

  it('renders nothing and fetches nothing for a non-operator', () => {
    const container = renderSlot({
      user_can_manage: false,
      user_is_event_operator: false,
    });
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId('ops-notices-card')).toBeNull();
    expect(fetchEventOpsNotices).not.toHaveBeenCalled();
  });
});
