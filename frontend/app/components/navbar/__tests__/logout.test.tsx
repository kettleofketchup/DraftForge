// @vitest-environment jsdom
import { act, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProfileButton } from '../login';

const { logout, clearUser } = vi.hoisted(() => ({
  logout: vi.fn<() => Promise<void>>(),
  clearUser: vi.fn<() => void>(),
}));

vi.mock('~/components/api/api', () => ({ logout }));
vi.mock('~/store/userStore', () => ({
  useUserStore: (selector: (state: object) => unknown) =>
    selector({ currentUser: { pk: 7, username: 'viewer' }, clearUser }),
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('~/components/teamdraft/DraftNotificationBadge', () => ({
  DraftNotificationBadge: () => null,
}));
vi.mock('~/components/user/UserAvatar', () => ({ UserAvatar: () => null }));
vi.mock('~/components/ui/dropdown-menu', () => {
  const Pass = ({ children }: { children?: ReactNode }) => (
    <div>{children}</div>
  );
  return {
    DropdownMenu: Pass,
    DropdownMenuContent: Pass,
    DropdownMenuItem: Pass,
    DropdownMenuLabel: Pass,
    DropdownMenuSeparator: () => null,
    DropdownMenuTrigger: Pass,
  };
});

describe('ProfileButton logout', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('clears the signed-in user only after the server session is gone', async () => {
    let finish: () => void = () => {};
    logout.mockReturnValue(new Promise<void>((resolve) => (finish = resolve)));
    render(
      <MemoryRouter>
        <ProfileButton />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId('navbarLogoutButton'));
    expect(logout).toHaveBeenCalledTimes(1);
    expect(clearUser).not.toHaveBeenCalled();

    await act(async () => finish());
    expect(clearUser).toHaveBeenCalledTimes(1);
  });

  it('still clears the user when the logout request fails', async () => {
    logout.mockRejectedValue(new Error('network'));
    render(
      <MemoryRouter>
        <ProfileButton />
      </MemoryRouter>,
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId('navbarLogoutButton'));
    });
    expect(clearUser).toHaveBeenCalledTimes(1);
  });
});
