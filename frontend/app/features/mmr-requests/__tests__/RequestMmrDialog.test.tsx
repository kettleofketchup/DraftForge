// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { toast } from 'sonner';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import api from '~/components/api/axios';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import { RequestMmrDialog, type RequestTarget } from '../RequestMmrDialog';
import { mmrRequest } from './fixtures';

vi.mock('~/components/api/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const ORG_TARGET: RequestTarget = {
  kind: 'org',
  orgUserPk: 117,
  orgName: 'Org X',
  gameType: 1,
  current: 4200,
  currentVerified: false,
};

const LEAGUE_TARGET: RequestTarget = {
  kind: 'league',
  leagueUserPk: 300,
  leagueName: 'Season 4',
  orgName: 'Org X',
  current: 4900,
  currentVerified: true,
};

beforeEach(() => {
  useUserStore.setState({ currentUser: { pk: 42 } as UserType });
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    writable: true,
    value: vi.fn(() => 'blob:preview'),
  });
  Object.defineProperty(URL, 'revokeObjectURL', {
    configurable: true,
    writable: true,
    value: vi.fn(),
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

function renderDialog(target: RequestTarget = ORG_TARGET) {
  const onOpenChange = vi.fn();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <RequestMmrDialog open onOpenChange={onOpenChange} target={target} />
      </TooltipProvider>
    </QueryClientProvider>,
  );
  return { onOpenChange };
}

function png(name = 'rank.png') {
  return new File(['png-bytes'], name, { type: 'image/png' });
}

function fill(value: string, file: File | null = png(), note = '') {
  fireEvent.change(screen.getByTestId('mmr-request-value'), {
    target: { value },
  });
  if (file) {
    fireEvent.change(screen.getByTestId('mmr-screenshot-input'), {
      target: { files: [file] },
    });
  }
  if (note) {
    fireEvent.change(screen.getByTestId('mmr-request-note'), {
      target: { value: note },
    });
  }
}

function submit() {
  fireEvent.click(screen.getByTestId('mmr-request-submit'));
}

function httpError(status: number, data: unknown) {
  return Object.assign(new Error(`HTTP ${status}`), {
    isAxiosError: true,
    response: { status, data },
  });
}

describe('RequestMmrDialog', () => {
  it('shows the target and current value', () => {
    renderDialog();
    expect(
      screen.getByText('Request MMR update — Org X · Dota 2'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('mmr-request-current')).toHaveTextContent('4200');
    expect(screen.getByTestId('mmr-badge-unverified')).toBeInTheDocument();
  });

  it('explains org vs league MMR', () => {
    renderDialog(LEAGUE_TARGET);
    expect(
      screen.getByText(
        'Org MMR is your default rating in Org X. League MMR is the value used for seeding in Season 4.',
      ),
    ).toBeInTheDocument();
  });

  it('blocks submit without a screenshot', async () => {
    renderDialog();
    fill('4800', null);
    submit();
    expect(
      await screen.findByText('A screenshot is required'),
    ).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it.each([
    ['0', 'MMR must be at least 1'],
    ['20001', 'MMR must be at most 20000'],
  ])('rejects %s', async (value, message) => {
    renderDialog();
    fill(value);
    submit();
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('posts multipart form data for an org target', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: mmrRequest() });
    const { onOpenChange } = renderDialog();
    const file = png();
    fill('4800', file, 'New season');
    submit();
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const [url, body] = vi.mocked(api.post).mock.calls[0];
    expect(url).toBe('/mmr-requests/');
    expect(body).toBeInstanceOf(FormData);
    const form = body as FormData;
    expect(form.get('target')).toBe('org');
    expect(form.get('org_user')).toBe('117');
    expect(form.get('game_type')).toBe('1');
    expect(form.get('requested_mmr')).toBe('4800');
    expect(form.get('note')).toBe('New season');
    const sent = form.get('screenshot');
    expect(sent).toBeInstanceOf(File);
    expect((sent as File).name).toBe('rank.png');
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(toast.success).toHaveBeenCalled();
  });

  it('posts the league membership for a league target', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: mmrRequest({ target: 'league' }),
    });
    renderDialog(LEAGUE_TARGET);
    fill('5100');
    submit();
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const form = vi.mocked(api.post).mock.calls[0][1] as FormData;
    expect(form.get('target')).toBe('league');
    expect(form.get('league_user')).toBe('300');
    expect(form.get('org_user')).toBeNull();
  });

  it('shows a pending conflict on 409', async () => {
    vi.mocked(api.post).mockRejectedValue(
      httpError(409, { error: 'pending_exists', request_id: 5 }),
    );
    const { onOpenChange } = renderDialog();
    fill('4800');
    submit();
    expect(
      await screen.findByText('You already have a pending request for this'),
    ).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it('puts a 413 on the screenshot field', async () => {
    vi.mocked(api.post).mockRejectedValue(
      httpError(413, { error: 'too_large' }),
    );
    renderDialog();
    fill('4800');
    submit();
    expect(
      await screen.findByText('The image must be 8 MB or smaller.'),
    ).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('puts a 400 screenshot code on the screenshot field', async () => {
    vi.mocked(api.post).mockRejectedValue(
      httpError(400, { screenshot: ['invalid_image'] }),
    );
    renderDialog();
    fill('4800');
    submit();
    expect(
      await screen.findByText("That file isn't a readable image."),
    ).toBeInTheDocument();
  });

  it('puts a 400 value error on the MMR field', async () => {
    vi.mocked(api.post).mockRejectedValue(
      httpError(400, { requested_mmr: ['Ensure this value is at most 20000'] }),
    );
    renderDialog();
    fill('4800');
    submit();
    expect(
      await screen.findByText('Ensure this value is at most 20000'),
    ).toBeInTheDocument();
  });

  it.each([429, 503, 507])('toasts on %s', async (status) => {
    vi.mocked(api.post).mockRejectedValue(httpError(status, {}));
    renderDialog();
    fill('4800');
    submit();
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });
});
