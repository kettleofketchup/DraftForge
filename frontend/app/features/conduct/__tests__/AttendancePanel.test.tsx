// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import { toast } from 'sonner';
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { searchUsers, type SearchUserResult } from '~/components/api/api';
import type { OrgFeatureAccess } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { getAttendance, putAttendance } from '../api';
import { AttendancePanel } from '../AttendancePanel';
import type { Attendance, AttendanceRow } from '../schemas';

vi.mock('../api', () => ({
  getAttendance: vi.fn(),
  putAttendance: vi.fn(),
}));
vi.mock('~/components/api/api', async () => {
  const actual = await vi.importActual<typeof import('~/components/api/api')>(
    '~/components/api/api',
  );
  return { ...actual, searchUsers: vi.fn() };
});
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
});

const ORG = 7;
const EVENT = 99;

const access: OrgFeatureAccess = makeOrgFeatureAccess({
  viewerPk: 5,
  canViewConduct: true,
  canViewOwnConduct: true,
  canViewConductDetails: true,
});

function row(
  orgUserPk: number,
  username: string,
  overrides: Partial<AttendanceRow> = {},
): AttendanceRow {
  return {
    member: {
      org_user_pk: orgUserPk,
      user_pk: orgUserPk + 100,
      username,
      nickname: null,
      avatarUrl: null,
    },
    org_user_pk: orgUserPk,
    signup_status: 'approved',
    outcome: 'attended',
    source: 'default',
    committed: true,
    virtual: false,
    finalized: false,
    voided: false,
    flag: null,
    set_by: null,
    reason: '',
    show_rate: 0.8,
    status: 'scored',
    ...overrides,
  };
}

function attendance(overrides: Partial<Attendance> = {}): Attendance {
  return {
    event_id: EVENT,
    state: 'in_progress',
    finalized_at: null,
    editable: true,
    editable_reason: null,
    rows: [row(11, 'alice'), row(12, 'bob'), row(13, 'carol')],
    ...overrides,
  };
}

function renderPanel(
  eventState = 'in_progress',
  panelAccess: OrgFeatureAccess = access,
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(
    <AttendancePanel
      orgId={ORG}
      eventId={EVENT}
      eventState={eventState}
      access={panelAccess}
    />,
    { wrapper },
  );
}

function searchResult(
  pk: number,
  username: string,
  membership: SearchUserResult['membership'],
): SearchUserResult {
  return { pk, username, nickname: null, membership };
}

beforeEach(() => {
  vi.mocked(getAttendance).mockReset();
  vi.mocked(putAttendance).mockReset();
  vi.mocked(searchUsers).mockReset();
  vi.mocked(toast.error).mockReset();
});

afterEach(cleanup);

describe('AttendancePanel', () => {
  it('marks every selected row with a bulk action', async () => {
    vi.mocked(getAttendance).mockResolvedValue(attendance());
    renderPanel();
    await screen.findByTestId('attendance-row-11');
    fireEvent.click(screen.getByTestId('attendance-select-11'));
    fireEvent.click(screen.getByTestId('attendance-select-12'));
    fireEvent.click(screen.getByTestId('attendance-bulk-no-show'));
    expect(screen.getByTestId('attendance-outcome-11')).toHaveTextContent(
      'No-show',
    );
    expect(screen.getByTestId('attendance-outcome-12')).toHaveTextContent(
      'No-show',
    );
    expect(screen.getByTestId('attendance-outcome-13')).toHaveTextContent(
      'Attended',
    );
  });

  it('select-all reaches all 30 rows and keeps them in the DOM', async () => {
    const rows = Array.from({ length: 30 }, (_, i) =>
      row(i + 1, `member${String(i + 1).padStart(2, '0')}`),
    );
    vi.mocked(getAttendance).mockResolvedValue(attendance({ rows }));
    renderPanel();
    await screen.findByTestId('attendance-row-30');
    fireEvent.click(screen.getByTestId('attendance-select-all'));
    fireEvent.click(screen.getByTestId('attendance-bulk-no-show'));
    for (let pk = 1; pk <= 30; pk++) {
      expect(screen.getByTestId(`attendance-outcome-${pk}`)).toHaveTextContent(
        'No-show',
      );
    }
  });

  it('requires a reason and sends one batch on confirm', async () => {
    vi.mocked(getAttendance).mockResolvedValue(attendance());
    vi.mocked(putAttendance).mockResolvedValue(attendance());
    renderPanel();
    await screen.findByTestId('attendance-row-11');
    fireEvent.click(screen.getByTestId('attendance-select-11'));
    fireEvent.click(screen.getByTestId('attendance-bulk-no-show'));
    fireEvent.click(screen.getByTestId('attendance-save'));

    await screen.findByTestId('conduct-reason-dialog');
    const input = screen.getByTestId('conduct-reason-input');
    const confirm = screen.getByTestId('conduct-reason-confirm');
    fireEvent.change(input, { target: { value: 'ab' } });
    expect(confirm).toBeDisabled();
    fireEvent.change(input, { target: { value: 'late' } });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);

    await waitFor(() => expect(putAttendance).toHaveBeenCalledTimes(1));
    expect(putAttendance).toHaveBeenCalledWith(ORG, EVENT, {
      changes: [{ org_user_pk: 11, outcome: 'no_show' }],
      reason: 'late',
    });
  });

  it('sends an expected member without an org membership by user_pk', async () => {
    const legacy = row(14, 'dave', { virtual: true, outcome: 'pending' });
    legacy.org_user_pk = null;
    legacy.member = { ...legacy.member, org_user_pk: null };
    vi.mocked(getAttendance).mockResolvedValue(
      attendance({ rows: [row(11, 'alice'), legacy] }),
    );
    vi.mocked(putAttendance).mockResolvedValue(attendance());
    renderPanel();
    await screen.findByTestId('attendance-row-user-114');
    fireEvent.click(screen.getByTestId('attendance-select-user-114'));
    fireEvent.click(screen.getByTestId('attendance-bulk-no-show'));
    expect(screen.getByTestId('attendance-outcome-user-114')).toHaveTextContent(
      'No-show',
    );
    fireEvent.click(screen.getByTestId('attendance-save'));
    await screen.findByTestId('conduct-reason-dialog');
    fireEvent.change(screen.getByTestId('conduct-reason-input'), {
      target: { value: 'never joined' },
    });
    fireEvent.click(screen.getByTestId('conduct-reason-confirm'));

    await waitFor(() => expect(putAttendance).toHaveBeenCalledTimes(1));
    expect(putAttendance).toHaveBeenCalledWith(ORG, EVENT, {
      changes: [{ user_pk: 114, outcome: 'no_show' }],
      reason: 'never joined',
    });
  });

  it('is read-only when the event is not editable', async () => {
    vi.mocked(getAttendance).mockResolvedValue(
      attendance({
        state: 'cancelled',
        editable: false,
        editable_reason:
          'This event was cancelled. Reopen and complete it to record attendance.',
      }),
    );
    renderPanel('cancelled');
    const note = await screen.findByTestId('attendance-readonly');
    expect(note).toHaveTextContent('Voided, event cancelled');
    expect(note).toHaveTextContent('Reopen and complete it');
    expect(screen.queryAllByRole('combobox')).toHaveLength(0);
    expect(screen.queryByTestId('attendance-select-all')).toBeNull();
    expect(screen.queryByTestId('attendance-save')).toBeNull();
  });

  it('shows the finalized banner once attendance is finalized', async () => {
    vi.mocked(getAttendance).mockResolvedValue(
      attendance({ state: 'completed', finalized_at: '2026-11-18T22:00:00Z' }),
    );
    renderPanel('completed');
    expect(await screen.findByTestId('attendance-finalized')).toHaveTextContent(
      'Edits are audited',
    );
  });

  it('renders flag chips', async () => {
    vi.mocked(getAttendance).mockResolvedValue(
      attendance({
        rows: [
          row(11, 'alice', {
            outcome: 'pending',
            flag: 'roll_call_unconfirmed',
          }),
          row(12, 'bob', {
            signup_status: 'dropped',
            outcome: 'pending',
            flag: 'dropped_unattributed',
          }),
        ],
      }),
    );
    renderPanel();
    expect(
      (await screen.findAllByText('Did not confirm at roll call')).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText('Dropped, needs review').length).toBeGreaterThan(
      0,
    );
  });

  it('shows a virtual row as attended by default', async () => {
    vi.mocked(getAttendance).mockResolvedValue(
      attendance({
        rows: [row(11, 'alice', { outcome: 'pending', virtual: true })],
      }),
    );
    renderPanel();
    expect(
      await screen.findByTestId('attendance-outcome-11'),
    ).toHaveTextContent('Attended (default)');
  });

  it('shows a walk-in search failure', async () => {
    vi.mocked(getAttendance).mockResolvedValue(attendance());
    vi.mocked(searchUsers).mockRejectedValue({
      response: { status: 500, data: { detail: 'Search is down' } },
    });
    renderPanel();
    await screen.findByTestId('attendance-row-11');
    fireEvent.click(screen.getByTestId('attendance-add-walkin'));
    fireEvent.change(await screen.findByTestId('attendance-walkin-search'), {
      target: { value: 'wal' },
    });

    expect(
      await screen.findByTestId('attendance-walkin-error'),
    ).toHaveTextContent('Search is down');
    expect(screen.queryByTestId('attendance-walkin-empty')).toBeNull();
  });

  it('shows searching while the walk-in search runs', async () => {
    vi.mocked(getAttendance).mockResolvedValue(attendance());
    vi.mocked(searchUsers).mockReturnValue(new Promise(() => {}));
    renderPanel();
    await screen.findByTestId('attendance-row-11');
    fireEvent.click(screen.getByTestId('attendance-add-walkin'));
    fireEvent.change(await screen.findByTestId('attendance-walkin-search'), {
      target: { value: 'wal' },
    });

    expect(
      await screen.findByTestId('attendance-walkin-searching'),
    ).toHaveTextContent('Searching...');
  });

  it('adds a walk-in from org members only and saves it', async () => {
    vi.mocked(getAttendance).mockResolvedValue(attendance());
    vi.mocked(putAttendance).mockResolvedValue(attendance());
    vi.mocked(searchUsers).mockResolvedValue([
      searchResult(50, 'walker', 'org'),
      searchResult(51, 'outsider', 'other_org'),
      searchResult(111, 'alice', 'org'),
    ]);
    renderPanel();
    await screen.findByTestId('attendance-row-11');
    fireEvent.click(screen.getByTestId('attendance-add-walkin'));
    fireEvent.change(await screen.findByTestId('attendance-walkin-search'), {
      target: { value: 'wal' },
    });

    const option = await screen.findByTestId('attendance-walkin-option-50');
    expect(searchUsers).toHaveBeenCalledWith('wal', ORG);
    expect(screen.queryByTestId('attendance-walkin-option-51')).toBeNull();
    expect(screen.queryByTestId('attendance-walkin-option-111')).toBeNull();
    fireEvent.click(option);

    expect(
      await screen.findByTestId('attendance-row-walkin-50'),
    ).toHaveTextContent('Walk-in');
    fireEvent.click(screen.getByTestId('attendance-save'));
    fireEvent.change(await screen.findByTestId('conduct-reason-input'), {
      target: { value: 'filled in' },
    });
    fireEvent.click(screen.getByTestId('conduct-reason-confirm'));

    await waitFor(() => expect(putAttendance).toHaveBeenCalledTimes(1));
    expect(putAttendance).toHaveBeenCalledWith(ORG, EVENT, {
      changes: [{ user_pk: 50, outcome: 'attended' }],
      reason: 'filled in',
    });
  });

  it('event staff who are not org staff get no Add walk-in button', async () => {
    vi.mocked(getAttendance).mockResolvedValue(attendance());
    renderPanel(
      'in_progress',
      makeOrgFeatureAccess({ viewerPk: 5, canViewConduct: true }),
    );
    await screen.findByTestId('attendance-row-11');
    expect(screen.getByTestId('attendance-bulk-no-show')).toBeInTheDocument();
    expect(screen.queryByTestId('attendance-add-walkin')).toBeNull();
    expect(screen.queryByTestId('attendance-walkin-search')).toBeNull();
  });

  it('bulk late cancel and excuse set those outcomes', async () => {
    vi.mocked(getAttendance).mockResolvedValue(attendance());
    renderPanel();
    await screen.findByTestId('attendance-row-11');
    expect(screen.getByTestId('attendance-bulk-late-cancel')).toHaveTextContent(
      'Mark late cancel',
    );
    expect(screen.getByTestId('attendance-bulk-attended')).toHaveTextContent(
      'Mark attended',
    );
    fireEvent.click(screen.getByTestId('attendance-select-11'));
    fireEvent.click(screen.getByTestId('attendance-bulk-late-cancel'));
    fireEvent.click(screen.getByTestId('attendance-select-12'));
    fireEvent.click(screen.getByTestId('attendance-bulk-excused'));
    expect(screen.getByTestId('attendance-outcome-11')).toHaveTextContent(
      'Late cancel',
    );
    expect(screen.getByTestId('attendance-outcome-12')).toHaveTextContent(
      'Excused',
    );
    expect(screen.getByTestId('attendance-save')).toHaveTextContent('Save (2)');
  });

  it('clears the selection after a bulk action', async () => {
    vi.mocked(getAttendance).mockResolvedValue(attendance());
    renderPanel();
    await screen.findByTestId('attendance-row-11');
    fireEvent.click(screen.getByTestId('attendance-select-11'));
    fireEvent.click(screen.getByTestId('attendance-bulk-no-show'));
    expect(screen.getByTestId('attendance-bulk-no-show')).toBeDisabled();
  });

  it('a failed save keeps the draft and toasts the API error', async () => {
    vi.mocked(getAttendance).mockResolvedValue(attendance());
    vi.mocked(putAttendance).mockRejectedValue({
      response: {
        status: 400,
        data: { detail: 'This event was cancelled.' },
      },
    });
    renderPanel();
    await screen.findByTestId('attendance-row-11');
    fireEvent.click(screen.getByTestId('attendance-select-11'));
    fireEvent.click(screen.getByTestId('attendance-bulk-no-show'));
    fireEvent.click(screen.getByTestId('attendance-save'));
    fireEvent.change(await screen.findByTestId('conduct-reason-input'), {
      target: { value: 'Left early' },
    });
    fireEvent.click(screen.getByTestId('conduct-reason-confirm'));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('This event was cancelled.'),
    );
    expect(screen.getByTestId('conduct-reason-dialog')).toBeInTheDocument();
    expect(screen.getByTestId('conduct-reason-input')).toHaveValue(
      'Left early',
    );
    expect(screen.getByTestId('attendance-outcome-11')).toHaveTextContent(
      'No-show',
    );
    expect(screen.getByTestId('attendance-save')).toHaveTextContent('Save (1)');
  });

  it('a completed event that was never tracked shows the not-tracked note', async () => {
    vi.mocked(getAttendance).mockResolvedValue(
      attendance({
        state: 'completed',
        editable: false,
        editable_reason: 'Attendance was not tracked for this event.',
      }),
    );
    renderPanel('completed');
    const note = await screen.findByTestId('attendance-readonly');
    expect(note).toHaveTextContent('Read-only');
    expect(note).toHaveTextContent(
      'Attendance was not tracked for this event.',
    );
    expect(screen.queryByTestId('attendance-bulk-no-show')).toBeNull();
  });

  it('Save is disabled with no changes', async () => {
    vi.mocked(getAttendance).mockResolvedValue(attendance());
    renderPanel();
    await screen.findByTestId('attendance-row-11');
    expect(screen.getByTestId('attendance-save')).toBeDisabled();
    expect(screen.getByTestId('attendance-discard')).toBeDisabled();
  });

  it('shows the load error', async () => {
    vi.mocked(getAttendance).mockRejectedValue({
      response: { status: 403, data: { detail: 'Not allowed' } },
    });
    renderPanel();
    expect(await screen.findByTestId('attendance-error')).toHaveTextContent(
      'Not allowed',
    );
  });
});
