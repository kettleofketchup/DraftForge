// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { useUserCacheStore } from '~/store/userCacheStore';
import { Leaderboard } from '../Leaderboard';
import type { LeaderboardResponse, LeaderboardRow } from '../schemas';

function row(guildNickname: string | null): LeaderboardRow {
  return {
    org_user_pk: 30,
    user_pk: 3,
    username: 'u',
    discordNickname: 'Gwaihir',
    guildNickname,
    avatarUrl: null,
    points: 10,
    entries: 1,
  };
}

function data(r: LeaderboardRow): LeaderboardResponse {
  return {
    period: 'all',
    total: 1,
    rows_visible: true,
    rows: [r],
    own_row: null,
  };
}

function renderBoard(r: LeaderboardRow, orgId: number) {
  return render(
    <Leaderboard
      data={data(r)}
      orgId={orgId}
      viewerPk={null}
      membersPrivate={false}
      onSelectMember={() => {}}
    />,
  );
}

beforeEach(() => useUserCacheStore.getState().reset());

describe('Leaderboard names', () => {
  it("shows the member's server nickname for the org", () => {
    renderBoard(row('DragonClaw'), 7);
    const tableRow = screen.getByTestId('contributions-row-30');
    expect(tableRow.textContent).toContain('DragonClaw');
    expect(tableRow.textContent).not.toContain('Gwaihir');
    expect(tableRow.getAttribute('aria-label')).toBe(
      "View DragonClaw's contributions",
    );
  });

  it('falls back to the global Discord name without a server nickname', () => {
    renderBoard(row(null), 7);
    expect(screen.getByTestId('contributions-row-30').textContent).toContain(
      'Gwaihir',
    );
  });

  it('never shows another org nickname cached for the same user', () => {
    useUserCacheStore
      .getState()
      .upsert([{ pk: 3, username: 'u', guildNickname: 'Other' } as never], {
        orgId: 8,
      });
    renderBoard(row(null), 7);
    const text = screen.getByTestId('contributions-row-30').textContent;
    expect(text).toContain('Gwaihir');
    expect(text).not.toContain('Other');
  });
});
