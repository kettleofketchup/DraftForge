// @vitest-environment jsdom
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Metric, StandingLeaderboard, StandingRow } from '../schemas';
import {
  StandingLeaderboard as StandingLeaderboardTable,
  type StandingLeaderboardProps,
} from '../StandingLeaderboard';
import { toStandingTableRows } from '../standingLeaderboardColumns';

const POINTS: Metric = {
  key: 'points',
  label: 'Points',
  format: 'int',
  periodic: true,
  default: true,
};
const ENTRIES: Metric = {
  key: 'entries',
  label: 'Entries',
  format: 'int',
  periodic: true,
  default: false,
};
const SHOW_RATE: Metric = {
  key: 'show_rate',
  label: 'Show rate',
  format: 'percent',
  periodic: false,
  default: true,
};

function row(
  orgUserPk: number,
  value: number | null,
  sample = 3,
  status: StandingRow['status'] = 'ranked',
): StandingRow {
  return {
    member: {
      org_user_pk: orgUserPk,
      user_pk: orgUserPk + 100,
      username: `user${orgUserPk}`,
      nickname: null,
      avatarUrl: null,
    },
    value,
    sample,
    status,
  };
}

function board(
  overrides: Partial<StandingLeaderboard> = {},
): StandingLeaderboard {
  return {
    track: 'contribution',
    metric: POINTS,
    period: 'all',
    total: 20,
    rows: [row(1, 12), row(2, 8)],
    rows_visible: true,
    own_row: null,
    own_private: false,
    ...overrides,
  };
}

function renderBoard(overrides: Partial<StandingLeaderboardProps> = {}) {
  const onOpen = vi.fn();
  const props: StandingLeaderboardProps = {
    board: board(),
    testIdPrefix: 'contributions',
    sampleLabel: 'Entries',
    totalUnit: 'points',
    emptyLabel: 'No contributions in this period',
    boardOpen: true,
    viewerPk: null,
    membersPrivate: false,
    canOpen: () => true,
    onOpen,
    ...overrides,
  };
  render(<StandingLeaderboardTable {...props} />);
  return { onOpen };
}

function cells(testId: string): string[] {
  return within(screen.getByTestId(testId))
    .getAllByRole('cell')
    .map((c) => c.textContent ?? '');
}

describe('toStandingTableRows', () => {
  it('ties share a rank', () => {
    const rows = toStandingTableRows(
      board({
        rows: [row(1, 0.9, 3), row(2, 0.9, 3), row(3, 0.8, 3), row(4, 0.8, 4)],
      }),
      null,
    );
    expect(rows.map((r) => r.rank)).toEqual([1, 1, 2, 3]);
  });

  it('marks the own row by own_row or viewer pk', () => {
    const rows = toStandingTableRows(
      board({ rows: [row(1, 5), row(2, 4)], own_row: row(2, 4) }),
      101,
    );
    expect(rows.map((r) => r.own)).toEqual([true, true]);
  });
});

describe('StandingLeaderboard', () => {
  it('numbers ranked rows and leaves new rows unranked', () => {
    renderBoard({
      board: board({
        metric: SHOW_RATE,
        total: null,
        rows: [row(1, 0.9), row(2, 0.8), row(3, null, 1, 'new')],
      }),
      testIdPrefix: 'conduct',
      sampleLabel: 'Events',
    });
    expect(cells('conduct-row-1')[0]).toBe('1');
    expect(cells('conduct-row-2')[0]).toBe('2');
    expect(cells('conduct-row-3')[0]).toBe('—');
  });

  it('formats a new row as New without a rank', () => {
    renderBoard({
      board: board({
        metric: SHOW_RATE,
        total: null,
        rows: [row(3, 0.85, 1, 'new')],
      }),
      testIdPrefix: 'conduct',
    });
    expect(screen.getByTestId('conduct-row-3-value')).toHaveTextContent('New');
    expect(cells('conduct-row-3')[0]).toBe('—');
  });

  it('ties share a rank', () => {
    renderBoard({
      board: board({
        rows: [row(1, 9, 3), row(2, 9, 3), row(3, 8, 3), row(4, 8, 2)],
      }),
    });
    expect(
      [1, 2, 3, 4].map((pk) => cells(`contributions-row-${pk}`)[0]),
    ).toEqual(['1', '1', '2', '3']);
  });

  it('shows the total card only when total is not null', () => {
    renderBoard();
    expect(screen.getByTestId('contributions-org-total')).toHaveTextContent(
      /^20\s*points$/,
    );
  });

  it('omits the total card when total is null', () => {
    renderBoard({
      board: board({ metric: SHOW_RATE, total: null }),
      testIdPrefix: 'conduct',
      totalUnit: null,
    });
    expect(screen.queryByTestId('conduct-org-total')).toBeNull();
  });

  it('entries metric keeps the total labelled in points', () => {
    renderBoard({ board: board({ metric: ENTRIES }) });
    const total = screen.getByTestId('contributions-org-total');
    expect(total).toHaveTextContent(/^20\s*points$/);
    expect(total).not.toHaveTextContent('entries');
  });

  it('shows the private note with the own row for a private-org member', () => {
    renderBoard({
      board: board({ rows: [], rows_visible: false, own_row: row(2, 3) }),
      membersPrivate: true,
      viewerPk: 102,
    });
    expect(
      screen.getByTestId('contributions-members-private'),
    ).toHaveTextContent('only your own standing is shown');
    const own = screen.getByTestId('contributions-row-2');
    expect(own).toHaveAttribute('data-own', 'true');
    expect(own).toHaveAttribute('aria-current', 'true');
    expect(own.className).toContain('bg-primary/10');
    expect(own).toHaveTextContent('(you)');
  });

  it('shows the private-feedback note instead of the own-only variant', () => {
    renderBoard({
      board: board({
        rows: [],
        rows_visible: false,
        own_row: row(2, 3),
        own_private: true,
      }),
      membersPrivate: true,
      viewerPk: 102,
    });
    expect(screen.getByTestId('standing-own-private')).toHaveTextContent(
      'Your org keeps captain feedback private.',
    );
    expect(
      screen.getByTestId('contributions-members-private'),
    ).not.toHaveTextContent('only your own standing is shown');
  });

  it('shows the private-feedback note above visible rows', () => {
    renderBoard({ board: board({ own_private: true }), viewerPk: 102 });
    const note = screen.getByTestId('standing-own-private');
    const icon = note.querySelector('svg');
    expect(icon).toHaveAttribute('aria-hidden', 'true');
    expect(icon).toHaveClass('size-4');
    expect(screen.getByTestId('contributions-row-1')).toBeInTheDocument();
  });

  it('shows no private-feedback note by default', () => {
    renderBoard();
    expect(screen.queryByTestId('standing-own-private')).toBeNull();
  });

  it('asks an anonymous viewer to sign in', () => {
    renderBoard({
      board: board({ rows: [], rows_visible: false }),
      viewerPk: null,
    });
    expect(
      screen.getByTestId('contributions-members-signin'),
    ).toBeInTheDocument();
  });

  it('tells an outsider only members can see it', () => {
    renderBoard({
      board: board({ rows: [], rows_visible: false }),
      viewerPk: 999,
    });
    expect(
      screen.getByTestId('contributions-members-only'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('contributions-empty')).toBeNull();
  });

  it('omits the rank column when rows are hidden', () => {
    renderBoard({
      board: board({ rows: [], rows_visible: false, own_row: row(2, 3) }),
      membersPrivate: true,
      viewerPk: 102,
    });
    expect(screen.queryByRole('columnheader', { name: '#' })).toBeNull();
    expect(cells('contributions-row-2')[1]).toBe('3');
  });

  it('shows no members note on a closed board', () => {
    renderBoard({
      board: board({
        track: 'conduct',
        metric: SHOW_RATE,
        total: null,
        rows: [],
        rows_visible: false,
        own_row: row(2, 0.9),
      }),
      testIdPrefix: 'conduct',
      boardOpen: false,
      membersPrivate: true,
      viewerPk: 102,
    });
    expect(screen.queryByTestId('conduct-members-only')).toBeNull();
    expect(screen.queryByTestId('conduct-members-private')).toBeNull();
    expect(screen.queryByTestId('conduct-members-signin')).toBeNull();
    expect(screen.getByTestId('conduct-row-2')).toBeInTheDocument();
  });

  it('renders the empty label it is given', () => {
    renderBoard({ board: board({ rows: [] }) });
    expect(screen.getByTestId('contributions-empty')).toHaveTextContent(
      'No contributions in this period',
    );
  });

  it('does not call onOpen for a row canOpen rejects', () => {
    const { onOpen } = renderBoard({
      canOpen: (r) => r.member.org_user_pk !== 2,
    });
    const rejected = screen.getByTestId('contributions-row-2');
    expect(rejected).not.toHaveAttribute('role');
    expect(rejected).not.toHaveAttribute('tabindex');
    fireEvent.click(rejected);
    fireEvent.keyDown(rejected, { key: 'Enter' });
    expect(onOpen).not.toHaveBeenCalled();
    expect(screen.getByTestId('contributions-row-1')).toHaveAttribute(
      'role',
      'button',
    );
  });

  it('opens on click', () => {
    const { onOpen } = renderBoard();
    fireEvent.click(screen.getByTestId('contributions-row-1'));
    expect(onOpen).toHaveBeenCalledWith(
      expect.objectContaining({ rank: 1, own: false }),
    );
  });

  it('opens with Enter on a focused row', () => {
    const { onOpen } = renderBoard();
    const target = screen.getByTestId('contributions-row-2');
    expect(target).toHaveAttribute('tabindex', '0');
    expect(target).toHaveAttribute('aria-label', "Open user2's details");
    target.focus();
    fireEvent.keyDown(target, { key: 'Enter' });
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(onOpen.mock.calls[0][0].member.org_user_pk).toBe(2);
  });

  it('opens with Space on a focused row', () => {
    const { onOpen } = renderBoard();
    const target = screen.getByTestId('contributions-row-1');
    target.focus();
    const notPrevented = fireEvent.keyDown(target, { key: ' ' });
    expect(notPrevented).toBe(false);
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('keeps 100 rows on one page', () => {
    renderBoard({
      board: board({
        rows: Array.from({ length: 100 }, (_, i) => row(i + 1, 200 - i)),
      }),
    });
    expect(screen.getByTestId('contributions-row-100')).toBeInTheDocument();
    expect(screen.queryByTestId('data-table-next')).toBeNull();
  });

  it('hides the sample column when sampleLabel is null', () => {
    renderBoard({ board: board({ metric: ENTRIES }), sampleLabel: null });
    expect(cells('contributions-row-1')).toHaveLength(3);
    expect(screen.getByRole('columnheader', { name: 'Entries' })).toBeTruthy();
  });

  it('shows the sample column with its label', () => {
    renderBoard();
    expect(cells('contributions-row-1')).toHaveLength(4);
    expect(screen.getByRole('columnheader', { name: 'Entries' })).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: 'Points' })).toBeTruthy();
  });
});
