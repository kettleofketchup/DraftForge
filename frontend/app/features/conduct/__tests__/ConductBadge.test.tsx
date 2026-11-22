// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { ConductBadge } from '../ConductBadge';
import { forecastMember } from './fixtures';

afterEach(cleanup);

describe('ConductBadge', () => {
  it('renders nothing without a forecast member', () => {
    const { container } = render(<ConductBadge member={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('labels a scored member with the show rate', () => {
    render(
      <ConductBadge
        member={forecastMember({ show_rate: 0.871, status: 'scored' })}
      />,
    );
    const badge = screen.getByTestId('conduct-badge');
    expect(badge).toHaveTextContent('Show rate 87%');
    expect(badge).toHaveAttribute('title', 'Show rate');
    expect(badge.querySelector('.sr-only')).toHaveTextContent('rate');
    expect(screen.queryByTestId('conduct-badge-tier')).not.toBeInTheDocument();
  });

  it('labels a new member New', () => {
    render(<ConductBadge member={forecastMember({ status: 'new' })} />);
    expect(screen.getByTestId('conduct-badge')).toHaveTextContent(
      'Show rate New',
    );
  });

  it.each([
    ['require_approval', 'Needs approval'],
    ['block', 'Blocked'],
  ] as const)('labels tier %s as %s', (tier, label) => {
    render(<ConductBadge member={forecastMember({ tier })} />);
    expect(screen.getByTestId('conduct-badge-tier')).toHaveTextContent(label);
  });

  it('wraps its badges right-aligned when its slot is narrow', () => {
    render(<ConductBadge member={forecastMember({ tier: 'block' })} />);
    const wrap = screen.getByTestId('conduct-badge').parentElement;
    expect(wrap).toHaveClass('flex-wrap', 'justify-end');
  });

  it('shows no approval badge for back_of_line', () => {
    render(<ConductBadge member={forecastMember({ tier: 'back_of_line' })} />);
    expect(screen.queryByTestId('conduct-badge-tier')).not.toBeInTheDocument();
  });
});
