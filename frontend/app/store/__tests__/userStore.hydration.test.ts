// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';

import api from '~/components/api/axios';

describe('userStore hydration under vitest', () => {
  it('does not send /current_user over the network on import', async () => {
    const adapter = vi.fn().mockRejectedValue(new Error('network disabled'));
    api.defaults.adapter = adapter;

    const { useUserStore } = await import('~/store/userStore');
    await vi.waitFor(() => expect(useUserStore.getState().hasHydrated).toBe(true));
    await new Promise((resolve) => setTimeout(resolve, 0));

    const urls = adapter.mock.calls.map(([config]) => config.url);
    expect(urls).not.toContain('/current_user');
    expect(useUserStore.getState().currentUser).toEqual({});
  });
});
