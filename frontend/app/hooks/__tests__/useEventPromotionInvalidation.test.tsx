// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { EventType } from '~/components/events/schemas';
import { promotionKeys } from '~/features/org-features/queryKeys';

const api = vi.hoisted(() => ({
  deleteEvent: vi.fn(),
  updateEvent: vi.fn(),
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  ...api,
}));

import { useEventActionMutation, useUpdateEventMutation } from '../useEvent';

const EVENT = 5;
const ORG = 3;
const OTHER_ORG = 4;
const event = { pk: EVENT, organization: ORG } as unknown as EventType;

const renderKey = (orgId: number, viewerPk: number | null) => [
  ...promotionKeys.all(orgId, viewerPk),
  'render',
  EVENT,
  1,
  9,
];

function setup(seedEvent = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const keys = {
    render: renderKey(ORG, 11),
    otherViewerRender: renderKey(ORG, 12),
    events: promotionKeys.events(ORG, 11),
    otherOrgRender: renderKey(OTHER_ORG, 11),
  };
  for (const key of Object.values(keys)) client.setQueryData(key, {});
  if (seedEvent) client.setQueryData(['event', EVENT], event);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const hook = renderHook(
    () => ({
      event: useEventActionMutation(EVENT),
      update: useUpdateEventMutation(EVENT),
    }),
    { wrapper },
  );
  const invalid = (key: readonly unknown[]) =>
    client.getQueryState(key)?.isInvalidated ?? false;
  return { hook, keys, invalid };
}

describe('event edits refresh rendered promo DMs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.updateEvent.mockResolvedValue(event);
    api.deleteEvent.mockResolvedValue(undefined);
  });

  it('updating the event invalidates the org’s promotion queries for every viewer', async () => {
    const { hook, keys, invalid } = setup();
    await act(() =>
      hook.result.current.update.mutateAsync({ name: 'Renamed' } as never),
    );
    expect(invalid(keys.render)).toBe(true);
    expect(invalid(keys.otherViewerRender)).toBe(true);
    expect(invalid(keys.events)).toBe(true);
    expect(invalid(keys.otherOrgRender)).toBe(false);
  });

  it('deleting a cached event invalidates its org’s promotion queries', async () => {
    const { hook, keys, invalid } = setup();
    await act(() => hook.result.current.event.deleteEvent.mutateAsync());
    expect(invalid(keys.render)).toBe(true);
    expect(invalid(keys.events)).toBe(true);
    expect(invalid(keys.otherOrgRender)).toBe(false);
  });

  it('deleting an uncached event leaves promotion queries alone', async () => {
    const { hook, keys, invalid } = setup(false);
    await act(() => hook.result.current.event.deleteEvent.mutateAsync());
    expect(invalid(keys.render)).toBe(false);
    expect(invalid(keys.otherOrgRender)).toBe(false);
  });
});
