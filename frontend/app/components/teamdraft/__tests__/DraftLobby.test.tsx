// @vitest-environment jsdom
import { fireEvent, render as rtlRender, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ReactElement } from 'react';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { TeamType } from '~/components/team/types';
import { DisplayName } from '~/components/user/avatar';
import { DraftLobby } from '../DraftLobby';
import { user } from './fixtures';

const render = (ui: ReactElement) => rtlRender(<TooltipProvider>{ui}</TooltipProvider>);

const teams = [7, 8, 9, 10].map((captain, i) => ({
  pk: i + 1,
  name: `Team ${i + 1}`,
  draft_order: i + 1,
  captain: user(captain),
  draft_is_ready: captain !== 10,
  draft_is_connected: captain !== 10,
})) as unknown as TeamType[];

const allReady = (): TeamType[] => teams.map((t) => ({ ...t, draft_is_ready: true }));

describe('DraftLobby', () => {
  it('renders a row per team with ready and connected dots', () => {
    render(<DraftLobby draftPk={1} teams={teams} currentUserPk={undefined} isStaff={false} />);
    expect(screen.getAllByTestId(/lobby-team-row-/)).toHaveLength(4);
    expect(screen.getByTestId('lobby-ready-check-4')).toHaveAttribute('data-state', 'not-ready');
    expect(screen.getByTestId('lobby-ready-check-1')).toHaveAttribute('data-state', 'ready');
    expect(screen.getByTestId('lobby-connected-dot-4')).toHaveAttribute('data-state', 'disconnected');
  });

  it('captain sees a Ready up toggle and no start control', () => {
    const onReadyToggle = vi.fn().mockResolvedValue({});
    render(<DraftLobby draftPk={1} teams={teams} currentUserPk={10} isStaff={false} onReadyToggle={onReadyToggle} />);
    expect(screen.queryByTestId('lobby-start-button')).toBeNull();
    expect(screen.getByTestId('lobby-ready-toggle')).toHaveTextContent('Ready up');
    fireEvent.click(screen.getByTestId('lobby-ready-toggle'));
    expect(onReadyToggle).toHaveBeenCalledWith(true);
  });

  it('ready captain sees Not ready and, once all are ready, Waiting for staff', () => {
    render(<DraftLobby draftPk={1} teams={allReady()} currentUserPk={7} isStaff={false} />);
    expect(screen.getByTestId('lobby-ready-toggle')).toHaveTextContent('Not ready');
    expect(screen.getByTestId('lobby-waiting-for-staff')).toHaveTextContent('Waiting for staff to start');
  });

  it('staff sees Force start with a confirm listing the not-ready captain', () => {
    const onStart = vi.fn().mockResolvedValue({});
    render(<DraftLobby draftPk={1} teams={teams} currentUserPk={999} isStaff onStart={onStart} />);
    const btn = screen.getByTestId('lobby-start-button');
    expect(btn).toHaveTextContent('Force start');
    fireEvent.click(btn);
    expect(screen.getByTestId('lobby-force-start-not-ready')).toHaveTextContent(DisplayName(teams[3].captain!));
    fireEvent.click(screen.getByTestId('lobby-force-start-confirm'));
    expect(onStart).toHaveBeenCalledTimes(1);
  });

  it('staff sees Start draft (no confirm) when everyone is ready', () => {
    const onStart = vi.fn().mockResolvedValue({});
    render(<DraftLobby draftPk={1} teams={allReady()} currentUserPk={999} isStaff onStart={onStart} />);
    expect(screen.getByTestId('lobby-start-button')).toHaveTextContent('Start draft');
    fireEvent.click(screen.getByTestId('lobby-start-button'));
    expect(screen.queryByTestId('lobby-force-start-dialog')).toBeNull();
    expect(onStart).toHaveBeenCalledTimes(1);
  });

  it('staff who is also a captain sees both controls', () => {
    render(<DraftLobby draftPk={1} teams={teams} currentUserPk={10} isStaff />);
    expect(screen.getByTestId('lobby-ready-toggle')).toBeTruthy();
    expect(screen.getByTestId('lobby-start-button')).toBeTruthy();
  });
});
