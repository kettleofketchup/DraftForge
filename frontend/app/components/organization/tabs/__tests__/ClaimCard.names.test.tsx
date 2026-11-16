// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ProfileClaimRequest } from '~/components/api/api';
import { ClaimCard } from '../ClaimCard';

const base: ProfileClaimRequest = {
  id: 1,
  claimer: 2,
  claimer_username: 'claimer',
  claimer_discord_id: null,
  claimer_avatar: null,
  target_user: 3,
  target_nickname: null,
  target_username: 'steam_76561198000000000',
  target_discordNickname: null,
  target_steamid: 76561198000000000,
  target_mmr: null,
  organization: 7,
  organization_name: 'Org',
  status: 'pending',
  reviewed_by: null,
  reviewed_by_username: null,
  rejection_reason: '',
  created_at: '2026-11-16T00:00:00Z',
  reviewed_at: null,
};

function renderCard(claim: ProfileClaimRequest) {
  render(
    <ClaimCard
      claim={claim}
      index={0}
      onApprove={() => {}}
      onReject={() => {}}
    />,
  );
  return screen.getByTestId('claim-card-1').textContent ?? '';
}

describe('ClaimCard target name', () => {
  it('shows the target Discord name first', () => {
    expect(
      renderCard({ ...base, target_discordNickname: 'Gwaihir' }),
    ).toContain('Gwaihir');
  });

  it('falls back to the target username', () => {
    expect(renderCard(base)).toContain('steam_76561198000000000');
  });

  it('falls back to the Steam ID without any name', () => {
    expect(renderCard({ ...base, target_username: null })).toContain(
      'Steam ID: 76561198000000000',
    );
  });

  it('ignores a stale site nickname', () => {
    const text = renderCard({ ...base, target_nickname: 'Site' });
    expect(text).not.toContain('Site');
  });
});
