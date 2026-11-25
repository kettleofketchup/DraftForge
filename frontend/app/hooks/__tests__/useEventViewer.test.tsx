// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { EventType } from '~/components/events/schemas';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';

const api = vi.hoisted(() => ({ getEvent: vi.fn() }));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  ...api,
}));

import { useEvent } from '../useEvent';

const EVENT = 5;
const ADMIN = 7;
const adminEvent = {
  id: EVENT,
  organization: 3,
  user_can_manage: true,
  user_can_manage_event_staff: true,
  manage_viewer_pk: ADMIN,
} as EventType;

function render() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(['event', EVENT], adminEvent);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(() => useEvent(EVENT), { wrapper });
}

describe('useEvent manage flags follow the viewer', () => {
  beforeEach(() => {
    api.getEvent.mockReset();
    useUserStore.setState({ currentUser: { pk: ADMIN } as UserType });
  });

  it('keeps the flags for the viewer they were computed for', async () => {
    const { result } = render();
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.user_can_manage).toBe(true);
    expect(result.current.data?.user_can_manage_event_staff).toBe(true);
  });

  it('drops cached admin flags as soon as the viewer logs out', async () => {
    const { result } = render();
    await waitFor(() =>
      expect(result.current.data?.user_can_manage).toBe(true),
    );
    act(() => useUserStore.setState({ currentUser: {} as UserType }));
    expect(result.current.data?.user_can_manage).toBe(false);
    expect(result.current.data?.user_can_manage_event_staff).toBe(false);
  });

  it('drops flags cached for another signed-in viewer', async () => {
    useUserStore.setState({ currentUser: { pk: 99 } as UserType });
    const { result } = render();
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.user_can_manage).toBe(false);
  });
});
