// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ConductLeaderboard,
  ConductLeaderboardTable,
  type ConductTableRow,
} from '../ConductLeaderboardTable';
import type { ConductLeaderboard as ConductLeaderboardData } from '../schemas';

function member(orgUserPk: number, userPk: number, username: string) {
  return {
    org_user_pk: orgUserPk,
    user_pk: userPk,
    username,
    nickname: null,
    avatarUrl: null,
  };
}

function tableRow(
  orgUserPk: number,
  username: string,
  showRate: number,
  countedEvents: number,
  rank: number,
): ConductTableRow {
  return {
    member: member(orgUserPk, orgUserPk + 100, username),
    show_rate: showRate,
    counted_events: countedEvents,
    rank,
    status: 'scored',
  };
}

const alice = tableRow(11, 'alice', 0.95, 4, 1);
const bob = tableRow(12, 'bob', 0.7, 9, 3);
const carol = tableRow(13, 'carol', 0.8, 6, 2);

function rowIds(): string[] {
  return screen
    .getAllByTestId(/^conduct-row-\d+$/)
    .map((r) => r.getAttribute('data-testid') ?? '');
}

afterEach(cleanup);

describe('ConductLeaderboardTable', () => {
  it('orders rows by rank by default', () => {
    render(
      <ConductLeaderboardTable
        rows={[bob, alice, carol]}
        ownPk={null}
        selectedPk={null}
        canSelect={false}
        onSelect={vi.fn()}
      />,
    );
    expect(rowIds()).toEqual([
      'conduct-row-11',
      'conduct-row-13',
      'conduct-row-12',
    ]);
    expect(screen.getByTestId('conduct-row-11-rate')).toHaveTextContent('95%');
  });

  it('re-sorts by events when that header is clicked', () => {
    render(
      <ConductLeaderboardTable
        rows={[bob, alice, carol]}
        ownPk={null}
        selectedPk={null}
        canSelect={false}
        onSelect={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId('data-table-sort-events'));
    expect(rowIds()).toEqual([
      'conduct-row-12',
      'conduct-row-13',
      'conduct-row-11',
    ]);
  });

  it('shows the empty message when there are no rows', () => {
    render(
      <ConductLeaderboardTable
        rows={[]}
        ownPk={null}
        selectedPk={null}
        canSelect={false}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByTestId('conduct-table')).toHaveTextContent(
      'No members have enough attendance history yet',
    );
  });

  it('lets staff select any row but members only their own', () => {
    const onSelect = vi.fn();
    const { rerender } = render(
      <ConductLeaderboardTable
        rows={[alice, bob]}
        ownPk={12}
        selectedPk={null}
        canSelect={false}
        onSelect={onSelect}
      />,
    );
    fireEvent.click(screen.getByTestId('conduct-row-11'));
    expect(onSelect).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('conduct-row-12'));
    expect(onSelect).toHaveBeenLastCalledWith(12);

    rerender(
      <ConductLeaderboardTable
        rows={[alice, bob]}
        ownPk={12}
        selectedPk={11}
        canSelect
        onSelect={onSelect}
      />,
    );
    fireEvent.click(screen.getByTestId('conduct-row-11'));
    expect(onSelect).toHaveBeenLastCalledWith(11);
    expect(screen.getByTestId('conduct-row-11')).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByTestId('conduct-row-12')).toHaveAttribute(
      'aria-pressed',
      'false',
    );
    expect(screen.getByTestId('conduct-row-11')).not.toHaveAttribute(
      'aria-selected',
    );
  });
});

describe('ConductLeaderboard', () => {
  it('shows the hidden-rows note and only the own row when rows are hidden', () => {
    const data: ConductLeaderboardData = {
      rows_visible: false,
      rows: [],
      new_members: [],
      own_row: {
        member: member(12, 5, 'me'),
        show_rate: 0.82,
        counted_events: 7,
        status: 'scored',
        rank: 4,
      },
    };
    render(
      <ConductLeaderboard
        data={data}
        viewerPk={5}
        membersPrivate
        selectedPk={null}
        canSelect={false}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByTestId('conduct-members-private')).toHaveTextContent(
      'only your own standing is shown',
    );
    expect(rowIds()).toEqual(['conduct-row-12']);
    expect(screen.getByTestId('conduct-row-12-rate')).toHaveTextContent('82%');
    expect(screen.queryByTestId('conduct-new-members')).not.toBeInTheDocument();
  });

  it('lists new members under the ranking', () => {
    const data: ConductLeaderboardData = {
      rows_visible: true,
      rows: [
        {
          member: member(11, 9, 'alice'),
          show_rate: 0.9,
          counted_events: 5,
          rank: 1,
        },
      ],
      new_members: [{ member: member(14, 8, 'newbie'), counted_events: 1 }],
      own_row: null,
    };
    render(
      <ConductLeaderboard
        data={data}
        viewerPk={null}
        membersPrivate={false}
        selectedPk={null}
        canSelect={false}
        onSelect={vi.fn()}
      />,
    );
    const list = screen.getByTestId('conduct-new-members');
    expect(list).toHaveTextContent('newbie');
    expect(list).toHaveTextContent('1 event');
    expect(rowIds()).toEqual(['conduct-row-11']);
  });
});
