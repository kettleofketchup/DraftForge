// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ProfileClaimRequest } from '~/components/api/api';
import { ClaimCard } from '../ClaimCard';

vi.mock('~/components/user/UserAvatar', () => ({ UserAvatar: () => null }));

function claim(over: Partial<ProfileClaimRequest>): ProfileClaimRequest {
  return {
    id: 1,
    claimer: 2,
    claimer_username: 'claimer',
    target_user: 3,
    target_nickname: 'Target',
    target_steamid: null,
    target_mmr: null,
    organization: 4,
    organization_name: 'Org',
    status: 'pending',
    created_at: '2026-01-01T00:00:00Z',
    ...over,
  } as ProfileClaimRequest;
}

function renderCard(c: ProfileClaimRequest) {
  render(
    <ClaimCard claim={c} index={0} onApprove={vi.fn()} onReject={vi.fn()} />,
  );
}

describe('ClaimCard target org MMR', () => {
  it('shows every game from target_game_mmrs', () => {
    renderCard(
      claim({ target_mmr: 4000, target_game_mmrs: { '1': 4000, '2': 1200 } }),
    );
    expect(screen.getByTestId('claim-target-mmr-dota2').textContent).toBe(
      'Dota 2 4000 MMR',
    );
    expect(screen.getByTestId('claim-target-mmr-deadlock').textContent).toBe(
      'Deadlock 1200 MMR',
    );
  });

  it('falls back to target_mmr as Dota 2', () => {
    renderCard(claim({ target_mmr: 3500 }));
    expect(screen.getByTestId('claim-target-mmr-dota2').textContent).toBe(
      'Dota 2 3500 MMR',
    );
    expect(screen.queryByTestId('claim-target-mmr-deadlock')).toBeNull();
  });

  it('shows No MMR when no game has a value', () => {
    renderCard(claim({ target_game_mmrs: { '1': 0, '2': 0 } }));
    expect(screen.getByText('No MMR')).toBeTruthy();
  });
});

describe('ClaimCard approved claim with merged target', () => {
  it('describes the merge instead of the deleted profile', () => {
    renderCard(
      claim({
        status: 'approved',
        target_user: null,
        target_nickname: null,
        target_steamid: null,
        target_mmr: null,
        target_game_mmrs: null,
        reviewed_by_username: 'admin',
        reviewed_at: '2026-01-02T00:00:00Z',
      }),
    );
    expect(screen.getByTestId('claim-target-merged').textContent).toBe(
      'Merged into claimer',
    );
    expect(screen.queryByText(/Steam ID: null/)).toBeNull();
    expect(screen.queryByText('No MMR')).toBeNull();
  });
});
