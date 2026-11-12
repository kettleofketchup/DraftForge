// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PickOrderReserve } from '../timer/PickOrderReserve';

const armed = (o = {}) => ({ kind: 'armed' as const, graceRemainingMs: 12_000, reserveByTeamId: { 1: 10_000, 2: 4_000 }, resumingRemainingMs: 0, expired: false, ...o });
const base = { teamPk: 2, isCurrent: false, draftStatus: 'drafting' as const, reserveTotalMs: 10_000 };

describe('PickOrderReserve', () => {
  it('renders nothing while unarmed', () => {
    const { container } = render(<PickOrderReserve {...base} countdown={{ kind: 'unarmed' }} />);
    expect(container).toBeEmptyDOMElement();
  });
  it('shows the team reserve and its share of the total', () => {
    render(<PickOrderReserve {...base} countdown={armed()} />);
    const chip = screen.getByTestId('draft-clock-reserve-2');
    expect(chip).toHaveTextContent('0:04');
    expect(chip).toHaveAttribute('data-pct', '40');
    expect(chip).toHaveAttribute('data-draining', 'false');
  });
  it('drains only for the current team once grace is over', () => {
    const { rerender } = render(<PickOrderReserve {...base} isCurrent countdown={armed({ graceRemainingMs: 0 })} />);
    expect(screen.getByTestId('draft-clock-reserve-2')).toHaveAttribute('data-draining', 'true');
    rerender(<PickOrderReserve {...base} countdown={armed({ graceRemainingMs: 0 })} />);
    expect(screen.getByTestId('draft-clock-reserve-2')).toHaveAttribute('data-draining', 'false');
    rerender(<PickOrderReserve {...base} isCurrent draftStatus="paused" countdown={armed({ graceRemainingMs: 0 })} />);
    expect(screen.getByTestId('draft-clock-reserve-2')).toHaveAttribute('data-draining', 'false');
  });
  it('pulses under 20% only when the total is known', () => {
    const low = armed({ graceRemainingMs: 0, reserveByTeamId: { 2: 1_000 } });
    const { rerender } = render(<PickOrderReserve {...base} isCurrent countdown={low} />);
    expect(screen.getByTestId('draft-clock-reserve-2').className).toContain('animate-reserve-critical');
    rerender(<PickOrderReserve {...base} isCurrent reserveTotalMs={0} countdown={low} />);
    expect(screen.getByTestId('draft-clock-reserve-2').className).not.toContain('animate-reserve-critical');
  });
});
