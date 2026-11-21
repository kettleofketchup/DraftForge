// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { OrganizationType } from '~/components/organization/schemas';
import type { OrgFeatureAccess } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { getAttendance, getForecast, putAttendance } from '../api';
import { EventConductSection } from '../EventConductSection';
import { attendance, forecast } from './fixtures';

vi.mock('../api', () => ({
  getAttendance: vi.fn(),
  getForecast: vi.fn(),
  putAttendance: vi.fn(),
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

const ORG = 7;

const staffAccess = makeOrgFeatureAccess({
  settled: true,
  viewerPk: 11,
  canViewConduct: true,
  canViewConductDetails: true,
  canManageConduct: true,
});

function org(features: string[] = ['conduct']): OrganizationType {
  return { pk: ORG, name: 'Org', features } as unknown as OrganizationType;
}

function renderSection({
  state,
  userCanManage = true,
  orgFeatures = ['conduct'],
  access = staffAccess,
}: {
  state: string;
  userCanManage?: boolean;
  orgFeatures?: string[];
  access?: OrgFeatureAccess;
}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(
    <EventConductSection
      event={{
        id: 5,
        organization: ORG,
        state: state as never,
        user_can_manage: userCanManage,
      }}
      org={org(orgFeatures)}
      access={access}
    />,
    { wrapper },
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('EventConductSection', () => {
  it('staff on an upcoming conduct event see the forecast only', async () => {
    vi.mocked(getForecast).mockResolvedValue(forecast());
    renderSection({ state: 'upcoming' });
    expect(
      await screen.findByTestId('conduct-forecast-summary'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('attendance-panel')).toBeNull();
    expect(getAttendance).not.toHaveBeenCalled();
  });

  it('roll call shows forecast and attendance', async () => {
    vi.mocked(getForecast).mockResolvedValue(forecast());
    vi.mocked(getAttendance).mockResolvedValue(
      attendance({ state: 'roll_call' }),
    );
    renderSection({ state: 'roll_call' });
    expect(
      await screen.findByTestId('conduct-forecast-summary'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('attendance-panel')).toBeInTheDocument();
    expect(getAttendance).toHaveBeenCalled();
  });

  it('a completed event shows attendance only', async () => {
    vi.mocked(getAttendance).mockResolvedValue(
      attendance({ state: 'completed' }),
    );
    renderSection({ state: 'completed' });
    expect(await screen.findByTestId('attendance-panel')).toBeInTheDocument();
    expect(screen.queryByTestId('conduct-forecast')).toBeNull();
    expect(getForecast).not.toHaveBeenCalled();
  });

  it('non-staff or a locked feature render nothing and fetch nothing', () => {
    const cases = [
      { state: 'roll_call', userCanManage: false },
      { state: 'roll_call', orgFeatures: [] },
      {
        state: 'roll_call',
        access: makeOrgFeatureAccess({ settled: false }),
      },
    ];
    for (const props of cases) {
      const { container, unmount } = renderSection(props);
      expect(container).toBeEmptyDOMElement();
      unmount();
    }
    expect(getForecast).not.toHaveBeenCalled();
    expect(getAttendance).not.toHaveBeenCalled();
    expect(putAttendance).not.toHaveBeenCalled();
  });
});
