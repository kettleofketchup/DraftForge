// @vitest-environment jsdom
import { act, render, screen } from '@testing-library/react';
import { hydrateRoot } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { UserClassType } from '~/components/user/types';
import { LoginAsUserButton } from '../LoginAsUserButton';

const shouldShowTestFeatures = vi.hoisted(() => vi.fn<() => boolean>());
vi.mock('~/lib/test-utils', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/lib/test-utils')>()),
  shouldShowTestFeatures,
}));

const user = { pk: 7, username: 'alice', discordId: '123' } as unknown as UserClassType;

describe('LoginAsUserButton', () => {
  it('renders nothing when test features are off', () => {
    shouldShowTestFeatures.mockReturnValue(false);
    const { container } = render(<LoginAsUserButton user={user} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the button when test features are on', () => {
    shouldShowTestFeatures.mockReturnValue(true);
    render(<LoginAsUserButton user={user} />);
    expect(screen.getByTestId('login-as-user-btn-7')).toBeInTheDocument();
  });

  it('renders nothing on the server, whatever the flag says', () => {
    shouldShowTestFeatures.mockReturnValue(true);
    expect(renderToString(<LoginAsUserButton user={user} />)).toBe('');
  });

  // The server cannot see window.playwright, so it may decide differently from
  // the client. The button must render nothing until hydration completes.
  it('hydrates without a mismatch when the client hides test features', async () => {
    shouldShowTestFeatures.mockReturnValue(true);
    const host = document.createElement('div');
    host.innerHTML = renderToString(<LoginAsUserButton user={user} />);
    document.body.appendChild(host);

    shouldShowTestFeatures.mockReturnValue(false);
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    const recoverable = vi.fn();
    const root = await act(async () =>
      hydrateRoot(host, <LoginAsUserButton user={user} />, { onRecoverableError: recoverable }),
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
});
