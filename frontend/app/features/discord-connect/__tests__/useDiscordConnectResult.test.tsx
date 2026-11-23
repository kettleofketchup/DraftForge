// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider, useLocation } from 'react-router';
import { toast } from 'sonner';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { organizationQueryKey } from '~/components/organization/hooks/useOrganization';
import { discordConnectKeys } from '../queries';
import { useDiscordConnectResult } from '../useDiscordConnectResult';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

let search = '';
function Page() {
  useDiscordConnectResult(4);
  search = useLocation().search;
  return null;
}

function renderAt(url: string) {
  const qc = new QueryClient();
  const invalidate = vi.spyOn(qc, 'invalidateQueries');
  const router = createMemoryRouter(
    [{ path: '/organizations/:id', Component: Page }],
    {
      initialEntries: [url],
    },
  );
  render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { invalidate };
}

afterEach(() => {
  vi.mocked(toast.success).mockReset();
  vi.mocked(toast.error).mockReset();
});

describe('useDiscordConnectResult', () => {
  it('toasts success, refreshes the org and strips the params', async () => {
    const { invalidate } = renderAt(
      '/organizations/4?settings=discord&discord=connected',
    );

    await waitFor(() => expect(search).toBe('?settings=discord'));
    expect(toast.success).toHaveBeenCalledWith('Discord server connected');
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: organizationQueryKey(4),
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: discordConnectKeys.botStatus(4),
    });
  });

  it('explains a known failure reason', async () => {
    renderAt(
      '/organizations/4?settings=discord&discord=error&reason=bot_missing',
    );

    await waitFor(() => expect(search).toBe('?settings=discord'));
    expect(toast.error).toHaveBeenCalledWith(
      expect.stringContaining("couldn't see that server"),
    );
  });

  it('falls back for an unknown reason', async () => {
    renderAt('/organizations/4?discord=error&reason=nope');

    await waitFor(() => expect(search).toBe(''));
    expect(toast.error).toHaveBeenCalledWith('Could not connect Discord.');
  });
});
