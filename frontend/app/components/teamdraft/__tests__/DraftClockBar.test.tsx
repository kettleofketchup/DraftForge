// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DisplayName } from '~/index';
import { DraftClockBar } from '../timer/DraftClockBar';
import { user } from './fixtures';

const armed = (o = {}) => ({ kind: 'armed' as const, graceRemainingMs: 12_000, reserveByTeamId: { 1: 10_000, 2: 4_000, 3: 10_000 }, resumingRemainingMs: 0, expired: false, ...o });
const teams = [{ teamPk: 1, teamName: 'T1', captain: user(7), isConnected: true }, { teamPk: 2, teamName: 'T2', captain: user(8), isConnected: true }, { teamPk: 3, teamName: 'T3', captain: null, isConnected: false }];
const base = { timerEnabled: true, clockArmed: true, draftStatus: 'drafting' as const, activeTeamPk: 1, teams, isMyTurn: false, canControl: true, isStaff: false, reserveTotalMs: 10_000, onPause: vi.fn(), onStartClock: vi.fn() };

describe('DraftClockBar', () => {
  it('renders nothing when the timer is disabled', () => { const { container } = render(<DraftClockBar {...base} timerEnabled={false} countdown={armed()} />); expect(container).toBeEmptyDOMElement(); });
  it('shows grace, per-team reserve and a dash for a captain-less team', () => {
    render(<DraftClockBar {...base} countdown={armed()} />);
    expect(screen.getByTestId('draft-clock-grace')).toHaveTextContent('0:12');
    expect(screen.getByTestId('draft-clock-reserve-2')).toHaveTextContent('0:04');
    expect(screen.getByTestId('draft-clock-reserve-3')).toHaveAttribute('data-empty', 'true');
    expect(screen.getByTestId('draft-clock-reserve-3')).not.toHaveTextContent('NaN');
  });
  it('sizes reserve as a percentage of reserveTotalMs', () => {
    const { rerender } = render(<DraftClockBar {...base} reserveTotalMs={10_000} countdown={armed()} />);
    expect(screen.getByTestId('draft-clock-reserve-2')).toHaveAttribute('data-pct', '40');
    expect(screen.getByTestId('draft-clock-reserve-1')).toHaveAttribute('data-pct', '100');
    rerender(<DraftClockBar {...base} reserveTotalMs={0} countdown={armed()} />);
    expect(screen.getByTestId('draft-clock-reserve-1')).toHaveAttribute('data-pct', '0');
  });
  it('pulses grace under 10 s', () => { render(<DraftClockBar {...base} countdown={armed({ graceRemainingMs: 9_000 })} />); expect(screen.getByTestId('draft-clock-grace').className).toContain('animate-grace-urgent'); });
  it('shows Pause only for controllers while armed and drafting', () => {
    const { rerender } = render(<DraftClockBar {...base} countdown={armed()} />);
    expect(screen.getByTestId('draft-clock-pause-button')).toBeVisible();
    rerender(<DraftClockBar {...base} canControl={false} countdown={armed()} />);
    expect(screen.queryByTestId('draft-clock-pause-button')).toBeNull();
    rerender(<DraftClockBar {...base} draftStatus="resuming" countdown={armed()} />);
    expect(screen.queryByTestId('draft-clock-pause-button')).toBeNull();
  });
  it('unarmed: No pick clock chip, no Pause, staff Start clock', () => {
    const { rerender } = render(<DraftClockBar {...base} clockArmed={false} countdown={{ kind: 'unarmed' }} />);
    expect(screen.getByTestId('draft-clock-unarmed')).toHaveTextContent('No pick clock');
    expect(screen.queryByTestId('draft-clock-pause-button')).toBeNull();
    expect(screen.queryByTestId('draft-clock-start-button')).toBeNull();
    rerender(<DraftClockBar {...base} clockArmed={false} isStaff countdown={{ kind: 'unarmed' }} />);
    expect(screen.getByTestId('draft-clock-start-button')).toBeVisible();
  });
  it('armed but no anchors yet: no "No pick clock" chip and no Start clock, grace shows a dash', () => {
    render(<DraftClockBar {...base} clockArmed isStaff countdown={{ kind: 'unarmed' }} />);
    expect(screen.queryByTestId('draft-clock-unarmed')).toBeNull();
    expect(screen.queryByTestId('draft-clock-start-button')).toBeNull();
    expect(screen.getByTestId('draft-clock-grace')).toHaveTextContent('—');
  });
  it('expired: waiting copy names the captain', () => { render(<DraftClockBar {...base} countdown={armed({ graceRemainingMs: 0, expired: true })} />); expect(screen.getByTestId('draft-clock-expired')).toHaveTextContent(`Clock expired — waiting for ${DisplayName(user(7))} or staff to pick`); });
});
