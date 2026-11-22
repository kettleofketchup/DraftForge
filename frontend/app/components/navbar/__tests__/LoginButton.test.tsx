// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LoginButton } from '../login';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

afterEach(() => {
  cleanup();
});

describe('LoginButton', () => {
  it('keeps a visible label below sm and the full label from sm up', () => {
    render(
      <MemoryRouter>
        <LoginButton />
      </MemoryRouter>,
    );
    const button = screen.getByTestId('navbarLoginButton');
    expect(button.getAttribute('aria-label')).toBe('login');

    const short = screen.getByText('login_short');
    expect(short.className).toContain('sm:hidden');
    expect(short.className).not.toMatch(/(^|\s)hidden/);

    const full = screen.getByText('login');
    expect(full.className).toMatch(/(^|\s)hidden(\s|$)/);
    expect(full.className).toContain('sm:inline');
  });
});
