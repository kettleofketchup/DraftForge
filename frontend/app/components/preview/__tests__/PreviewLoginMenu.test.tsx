// @vitest-environment jsdom
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { hydrateRoot } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PreviewLoginMenu } from '../PreviewLoginMenu';

const shouldShowTestFeatures = vi.hoisted(() => vi.fn<() => boolean>());
vi.mock('~/lib/test-utils', () => ({ shouldShowTestFeatures }));

describe('PreviewLoginMenu', () => {
  const fetchMock = vi.fn();
  const reloadMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset().mockResolvedValue(new Response(null, { status: 200 }));
    reloadMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('location', { ...window.location, reload: reloadMock });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders nothing when test features are off', () => {
    shouldShowTestFeatures.mockReturnValue(false);
    const { container } = render(<PreviewLoginMenu />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders three login buttons when test features are on', () => {
    shouldShowTestFeatures.mockReturnValue(true);
    render(<PreviewLoginMenu />);
    expect(screen.getByTestId('preview-login-admin')).toHaveTextContent('Login as admin');
    expect(screen.getByTestId('preview-login-staff')).toHaveTextContent('Login as staff');
    expect(screen.getByTestId('preview-login-user')).toHaveTextContent('Login as user');
  });

  it.each(['admin', 'staff', 'user'] as const)(
    'logs in as %s via the test endpoint and reloads once',
    async (role) => {
      shouldShowTestFeatures.mockReturnValue(true);
      render(<PreviewLoginMenu />);
      fireEvent.click(screen.getByTestId(`preview-login-${role}`));
      await waitFor(() => expect(reloadMock).toHaveBeenCalledTimes(1));
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(fetchMock).toHaveBeenCalledWith(
        `/api/tests/login-${role}/`,
        expect.objectContaining({ method: 'POST', credentials: 'include' }),
      );
    },
  );

  // The server cannot see window.playwright, so it may decide differently from
  // the client. The menu must render nothing until hydration completes.
  it('hydrates without a mismatch when the client hides test features', async () => {
    shouldShowTestFeatures.mockReturnValue(true);
    const host = document.createElement('div');
    host.innerHTML = renderToString(<PreviewLoginMenu />);
    document.body.appendChild(host);

    shouldShowTestFeatures.mockReturnValue(false);
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    const recoverable = vi.fn();
    const root = await act(async () =>
      hydrateRoot(host, <PreviewLoginMenu />, { onRecoverableError: recoverable }),
    );

    expect(recoverable).not.toHaveBeenCalled();
    expect(consoleError).not.toHaveBeenCalledWith(
      expect.stringContaining('Hydration failed'),
      expect.anything(),
    );
    expect(host).toBeEmptyDOMElement();
    act(() => root.unmount());
    host.remove();
    consoleError.mockRestore();
  });

  it('shows the buttons after hydration when test features are on', async () => {
    shouldShowTestFeatures.mockReturnValue(true);
    const host = document.createElement('div');
    host.innerHTML = renderToString(<PreviewLoginMenu />);
    document.body.appendChild(host);
    const recoverable = vi.fn();
    const root = await act(async () =>
      hydrateRoot(host, <PreviewLoginMenu />, { onRecoverableError: recoverable }),
    );

    expect(recoverable).not.toHaveBeenCalled();
    expect(within(host).getByTestId('preview-login-admin')).toBeInTheDocument();
    act(() => root.unmount());
    host.remove();
  });
});
