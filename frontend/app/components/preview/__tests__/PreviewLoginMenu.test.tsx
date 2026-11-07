// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
});
