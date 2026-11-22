// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { getForecast } from '../api';
import { ConductForecastCard } from '../ConductForecastCard';
import { forecast } from './fixtures';

vi.mock('../api', () => ({
  getForecast: vi.fn(),
}));

const access = makeOrgFeatureAccess({
  settled: true,
  viewerPk: 11,
  canViewConduct: true,
  canViewConductDetails: true,
  canManageConduct: true,
});

function wrap(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ConductForecastCard', () => {
  it('renders the summary, open seats, new members and pending approval', async () => {
    vi.mocked(getForecast).mockResolvedValue(
      forecast({
        expected: 23.6,
        pending_approval: 2,
        expected_open_seats: 5.6,
      }),
    );
    wrap(<ConductForecastCard orgId={1} eventId={7} access={access} />);

    expect(
      await screen.findByTestId('conduct-forecast-summary'),
    ).toHaveTextContent('30 signed up · expect ~24 (21–27)');
    expect(getForecast).toHaveBeenCalledWith(1, 7);
    expect(screen.getByTestId('conduct-forecast-open-seats')).toHaveTextContent(
      '~6 open seats',
    );
    expect(
      screen.getByTestId('conduct-forecast-new-members'),
    ).toHaveTextContent('3 new members');
    expect(
      screen.getByTestId('conduct-forecast-pending-approval'),
    ).toHaveTextContent('2 awaiting approval');
  });

  it('hides open seats without a capacity and pending when none', async () => {
    vi.mocked(getForecast).mockResolvedValue(
      forecast({
        capacity: null,
        expected_open_seats: null,
        pending_approval: 0,
        new_members: 1,
      }),
    );
    wrap(<ConductForecastCard orgId={1} eventId={7} access={access} />);

    await screen.findByTestId('conduct-forecast-summary');
    expect(
      screen.queryByTestId('conduct-forecast-open-seats'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('conduct-forecast-pending-approval'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId('conduct-forecast-new-members'),
    ).toHaveTextContent('1 new member');
  });

  it('shows the API error when the request fails', async () => {
    vi.mocked(getForecast).mockRejectedValue({
      response: { status: 500, data: { detail: 'Server error' } },
    });
    wrap(<ConductForecastCard orgId={1} eventId={7} access={access} />);

    expect(
      await screen.findByTestId('conduct-forecast-error'),
    ).toHaveTextContent('Server error');
  });
});
