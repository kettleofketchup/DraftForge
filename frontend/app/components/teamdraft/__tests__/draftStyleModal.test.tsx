// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { updateDraftOptions } from '~/components/api/tournamentAPI';
import { useUserStore } from '~/store/userStore';
import { DraftStyleModal } from '../buttons/draftStyleModal';

vi.mock('~/components/api/tournamentAPI', () => ({
  updateDraftOptions: vi.fn().mockResolvedValue({ pk: 1, draft: {} }),
}));
// Saving refreshes the predicted MMRs; the modal tests don't assert on them.
vi.mock('~/components/api/draftAPI', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/draftAPI')>()),
  getDraftStyleMMRs: vi.fn().mockResolvedValue({}),
}));
vi.mock('sonner', () => ({
  toast: { promise: vi.fn(), error: vi.fn(), success: vi.fn() },
}));

const options = (grace: number, reserve: number) => ({
  timer_enabled: true,
  grace_time_ms: grace,
  reserve_time_ms: reserve,
  timeout_action: 'skip_turn',
});
const tournament = (o?: ReturnType<typeof options>) =>
  ({ pk: 1, ...(o ? { draft_options: o } : {}) }) as never;

const seed = (staff: boolean, o?: ReturnType<typeof options>) =>
  useUserStore.setState({
    isStaff: () => staff,
    tournament: tournament(o),
    draft: undefined as never,
  });

const mount = () =>
  render(<DraftStyleModal externalOpen showTrigger={false} onExternalOpenChange={() => {}} />);

describe('DraftStyleModal draft options', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    vi.mocked(updateDraftOptions).mockClear();
  });
  afterEach(cleanup);

  it('defaults to seconds and Save is disabled while clean', () => {
    seed(true, options(20000, 10000));
    mount();
    expect(screen.getByTestId('draft-options-grace-s')).toHaveValue(20);
    expect(screen.getByTestId('draft-options-reserve-s')).toHaveValue(10);
    expect(screen.getByTestId('draft-options-save')).toBeDisabled();
  });

  it('saves a changed grace as ms', async () => {
    seed(true, options(20000, 10000));
    mount();
    fireEvent.change(screen.getByTestId('draft-options-grace-s'), { target: { value: '25' } });
    fireEvent.click(screen.getByTestId('draft-options-save'));
    await waitFor(() =>
      expect(updateDraftOptions).toHaveBeenCalledWith(1, {
        timer_enabled: true,
        grace_time_ms: 25000,
        reserve_time_ms: 10000,
      }),
    );
  });

  it('does not PATCH when Reserve is cleared', async () => {
    seed(true, options(20000, 10000));
    mount();
    fireEvent.change(screen.getByTestId('draft-options-reserve-s'), { target: { value: '' } });
    fireEvent.click(screen.getByTestId('draft-options-save'));
    await waitFor(() =>
      expect(screen.getByText(/Whole seconds only|Cannot be negative/)).toBeVisible(),
    );
    expect(updateDraftOptions).not.toHaveBeenCalled();
  });

  it('a clean form picks up options that arrive after mount; a dirty form keeps the edit', async () => {
    seed(true);
    mount();
    expect(screen.getByTestId('draft-options-grace-s')).toHaveValue(30);
    act(() => useUserStore.setState({ tournament: tournament(options(45000, 15000)) }));
    await waitFor(() => expect(screen.getByTestId('draft-options-grace-s')).toHaveValue(45));
    fireEvent.change(screen.getByTestId('draft-options-grace-s'), { target: { value: '50' } });
    act(() => useUserStore.setState({ tournament: tournament(options(60000, 15000)) }));
    expect(screen.getByTestId('draft-options-grace-s')).toHaveValue(50);
  });

  it('non-staff see no form', () => {
    seed(false, options(20000, 10000));
    mount();
    expect(screen.queryByTestId('draft-options-form')).toBeNull();
  });
});
