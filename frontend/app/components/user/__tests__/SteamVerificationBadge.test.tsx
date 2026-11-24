// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  SteamVerificationBadge,
  type SteamVerificationBadgeProps,
} from '../SteamVerificationBadge';

const mutation = vi.hoisted(() => ({
  mutate: vi.fn(),
  isPending: false,
  hookArgs: [] as unknown[],
}));
vi.mock('~/features/steam-verification', () => ({
  useSetSteamVerification: (userPk: number) => {
    mutation.hookArgs.push(userPk);
    return { mutate: mutation.mutate, isPending: mutation.isPending };
  },
}));

const base: SteamVerificationBadgeProps = {
  userPk: 7,
  steamAccountId: 123456,
  verified: false,
  existsChecked: true,
  canVerify: false,
};

function renderBadge(props: Partial<SteamVerificationBadgeProps> = {}) {
  return render(<SteamVerificationBadge {...base} {...props} />);
}

function openMenu() {
  fireEvent.pointerDown(screen.getByTestId('steam-verification-menu'), {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse',
  });
}

beforeEach(() => {
  mutation.mutate.mockReset();
  mutation.isPending = false;
  mutation.hookArgs = [];
});

afterEach(() => cleanup());

describe('SteamVerificationBadge', () => {
  it('renders nothing without a Friend ID', () => {
    const { container } = renderBadge({ steamAccountId: null });
    expect(container.innerHTML).toBe('');
  });

  it('shows Unverified with the Found on Steam tooltip', () => {
    renderBadge({ existsChecked: true });
    const badge = screen.getByTestId('steam-verification-unverified');
    expect(badge.textContent).toBe('Unverified');
    expect(badge.getAttribute('title')).toBe('Self-reported. Found on Steam.');
  });

  it('shows the Not checked tooltip when Steam never confirmed it', () => {
    renderBadge({ existsChecked: false });
    expect(
      screen.getByTestId('steam-verification-unverified').getAttribute('title'),
    ).toBe('Self-reported. Not checked against Steam.');
  });

  it('has no actions without canVerify', () => {
    renderBadge();
    expect(screen.queryByTestId('steam-verify-button')).toBeNull();
    expect(screen.queryByTestId('steam-profile-link')).toBeNull();
    expect(mutation.hookArgs).toEqual([]);
  });

  it('Verify posts the displayed Friend ID', () => {
    renderBadge({ canVerify: true });
    fireEvent.click(screen.getByTestId('steam-verify-button'));
    expect(mutation.hookArgs[0]).toBe(7);
    expect(mutation.mutate).toHaveBeenCalledWith({
      verified: true,
      steamAccountId: 123456,
    });
  });

  it('disables Verify while the mutation is pending', () => {
    mutation.isPending = true;
    renderBadge({ canVerify: true });
    expect(
      (screen.getByTestId('steam-verify-button') as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it('links the Steam profile by the 64-bit id', () => {
    renderBadge({ canVerify: true });
    expect(screen.getByTestId('steam-profile-link').getAttribute('href')).toBe(
      'https://steamcommunity.com/profiles/76561197960389184',
    );
  });

  it('hides the Verified state from non-staff viewers', () => {
    const { container } = renderBadge({
      verified: true,
      verifiedOrgName: 'Acme',
    });
    expect(container.innerHTML).toBe('');
  });

  it('shows the vouching org to staff', () => {
    renderBadge({
      verified: true,
      verifiedOrgName: 'Acme',
      verifiedAt: '2026-11-20T12:00:00Z',
      staffView: true,
    });
    const badge = screen.getByTestId('steam-verification-verified');
    expect(badge.textContent).toBe('Verified');
    expect(badge.getAttribute('title')).toMatch(/^Verified by Acme on /);
  });

  it('credits site staff when no org vouched', () => {
    renderBadge({ verified: true, verifiedOrgName: null, staffView: true });
    expect(
      screen.getByTestId('steam-verification-verified').getAttribute('title'),
    ).toMatch(/^Verified by site staff on /);
  });

  it('Mark unverified posts verified=false', async () => {
    renderBadge({ verified: true, canVerify: true });
    expect(screen.queryByTestId('steam-verify-button')).toBeNull();
    openMenu();
    fireEvent.click(await screen.findByTestId('steam-unverify-item'));
    expect(mutation.mutate).toHaveBeenCalledWith({
      verified: false,
      steamAccountId: 123456,
    });
  });

  it('becomes a button when onClick is given', () => {
    const onClick = vi.fn();
    renderBadge({ onClick });
    const badge = screen.getByTestId('steam-verification-unverified');
    expect(badge.tagName).toBe('BUTTON');
    fireEvent.click(badge);
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
