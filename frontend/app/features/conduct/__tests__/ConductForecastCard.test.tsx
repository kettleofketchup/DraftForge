// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { OrgFeatureAccess } from '~/features/org-features';
import { getForecast } from '../api';
import { ConductBadge } from '../ConductBadge';
import { ConductForecastCard } from '../ConductForecastCard';
import { DEFERRED_NOTE, type Forecast, type ForecastMember } from '../schemas';

vi.mock('../api', () => ({
  getForecast: vi.fn(),
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

const access: OrgFeatureAccess = {
  settled: true,
  viewerPk: 5,
  canUsePromotion: false,
  canManageTemplates: false,
  canManagePromoters: false,
  canViewContributions: false,
  canViewContributors: false,
  canManageContributions: false,
  canViewConduct: true,
  canViewOwnConduct: true,
  canViewConductDetails: true,
  canManageConduct: true,
};

function forecast(overrides: Partial<Forecast> = {}): Forecast {
  return {
    seat_holders: 30,
    expected: 24.2,
    low: 21,
    high: 27,
    waitlisted: 2,
    pending_approval: 0,
    capacity: 30,
    expected_open_seats: 5.8,
    new_members: 3,
    members: {},
    ...overrides,
  };
}

function member(overrides: Partial<ForecastMember> = {}): ForecastMember {
  return {
    show_rate: 0.79,
    status: 'scored',
    tier: 'ok',
    deferred: false,
    ...overrides,
  };
}

function wrap(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>{ui}</TooltipProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ConductForecastCard', () => {
  it('renders the exact forecast line, open seats and new members', async () => {
    vi.mocked(getForecast).mockResolvedValue(forecast());
    wrap(<ConductForecastCard orgId={1} eventId={7} access={access} />);

    expect(
      await screen.findByText('30 signed up · expect ~24 (21–27)'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('conduct-forecast')).toBeInTheDocument();
    expect(getForecast).toHaveBeenCalledWith(1, 7);
    expect(screen.getByTestId('conduct-forecast-open-seats')).toHaveTextContent(
      '~6 open seats',
    );
    expect(
      screen.getByTestId('conduct-forecast-new-members'),
    ).toHaveTextContent('3 new members');
  });

  it('hides awaiting approval when nobody is pending', async () => {
    vi.mocked(getForecast).mockResolvedValue(forecast({ pending_approval: 0 }));
    wrap(<ConductForecastCard orgId={1} eventId={7} access={access} />);

    await screen.findByText('30 signed up · expect ~24 (21–27)');
    expect(screen.queryByText(/awaiting approval/)).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('conduct-forecast-pending-approval'),
    ).not.toBeInTheDocument();
  });

  it('shows awaiting approval when members are pending', async () => {
    vi.mocked(getForecast).mockResolvedValue(forecast({ pending_approval: 2 }));
    wrap(<ConductForecastCard orgId={1} eventId={7} access={access} />);

    expect(
      await screen.findByTestId('conduct-forecast-pending-approval'),
    ).toHaveTextContent('2 awaiting approval');
  });

  it('shows the load error to staff', async () => {
    vi.mocked(getForecast).mockRejectedValue({
      response: { status: 500, data: { detail: 'Server error' } },
    });
    wrap(<ConductForecastCard orgId={1} eventId={7} access={access} />);

    expect(
      await screen.findByTestId('conduct-forecast-error'),
    ).toHaveTextContent('Server error');
  });

  it('does not fetch when disabled', () => {
    wrap(
      <ConductForecastCard
        orgId={1}
        eventId={7}
        access={access}
        enabled={false}
      />,
    );
    expect(getForecast).not.toHaveBeenCalled();
  });
});

describe('ConductBadge', () => {
  it('renders nothing without a forecast member', () => {
    wrap(<ConductBadge member={undefined} />);
    expect(screen.queryByTestId('conduct-badge')).not.toBeInTheDocument();
  });

  it('renders the show rate for a scored member', () => {
    wrap(<ConductBadge member={member()} />);
    expect(screen.getByTestId('conduct-badge')).toHaveTextContent(
      'Show rate 79%',
    );
    expect(
      screen.queryByTestId('conduct-badge-deferred'),
    ).not.toBeInTheDocument();
  });

  it('renders New for a new member', () => {
    wrap(<ConductBadge member={member({ status: 'new', show_rate: 0.85 })} />);
    expect(screen.getByTestId('conduct-badge')).toHaveTextContent('New');
  });

  it('renders Deferred with the exact note as name and tooltip', async () => {
    wrap(
      <ConductBadge
        member={member({ tier: 'back_of_line', deferred: true })}
      />,
    );
    const deferred = screen.getByTestId('conduct-badge-deferred');
    expect(deferred).toHaveTextContent('Deferred');
    expect(deferred).toHaveAttribute('role', 'note');
    expect(deferred).toHaveAccessibleName(DEFERRED_NOTE);

    fireEvent.focus(deferred);
    expect(await screen.findByRole('tooltip')).toHaveTextContent(DEFERRED_NOTE);
  });

  it('exposes the verbatim spec note', () => {
    expect(DEFERRED_NOTE).toBe(
      'Deferred by conduct: promoted after members without the flag',
    );
  });

  it.each(['require_approval', 'block'] as const)(
    'renders Needs approval for tier %s',
    (tier) => {
      wrap(<ConductBadge member={member({ tier })} />);
      expect(screen.getByTestId('conduct-badge-approval')).toHaveTextContent(
        'Needs approval',
      );
    },
  );

  it('shows no indicator for back_of_line members not deferred', () => {
    wrap(<ConductBadge member={member({ tier: 'back_of_line' })} />);
    expect(
      screen.queryByTestId('conduct-badge-deferred'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('conduct-badge-approval'),
    ).not.toBeInTheDocument();
  });
});
