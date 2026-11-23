// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { Toaster } from 'sonner';
import { describe, expect, it } from 'vitest';
import { useDiscordConnectResult } from '../useDiscordConnectResult';

function Page() {
  useDiscordConnectResult(4);
  return null;
}

describe('useDiscordConnectResult with a real Toaster', () => {
  it('shows the toast when the Toaster mounts after the page, as in root.tsx', async () => {
    const router = createMemoryRouter(
      [{ path: '/organizations/:id', Component: Page }],
      { initialEntries: ['/organizations/4?discord=connected'] },
    );
    render(
      <QueryClientProvider client={new QueryClient()}>
        <RouterProvider router={router} />
        <Toaster />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Discord server connected')).toBeTruthy();
  });
});
