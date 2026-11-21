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
    expect(screen.getByTestId('conduct-badge')).toHaveTextContent(
      'Show rate 87%',
    );
    expect(
      screen.queryByTestId('conduct-badge-approval'),
    ).not.toBeInTheDocument();
  });

  it('labels a new member New', () => {
    render(<ConductBadge member={forecastMember({ status: 'new' })} />);
    expect(screen.getByTestId('conduct-badge')).toHaveTextContent(
      'Show rate New',
    );
  });

  it.each(['require_approval', 'block'] as const)(
    'flags tier %s as needing approval',
    (tier) => {
      render(<ConductBadge member={forecastMember({ tier })} />);
      expect(screen.getByTestId('conduct-badge-approval')).toHaveTextContent(
        'Needs approval',
      );
    },
  );

  it('shows no approval badge for back_of_line', () => {
    render(<ConductBadge member={forecastMember({ tier: 'back_of_line' })} />);
    expect(
      screen.queryByTestId('conduct-badge-approval'),
    ).not.toBeInTheDocument();
  });
});
