// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import type { ReactElement } from 'react';
import { toast } from 'sonner';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { downloadSignupRecordsCsv } from '~/components/api/eventsAPI';
import { TooltipProvider } from '~/components/ui/tooltip';
import { ExportSignupRecordsButton } from '../ExportSignupRecordsButton';
import { ExportSignupRecordsDialog } from '../ExportSignupRecordsDialog';

const log = vi.hoisted(() => ({
  error: vi.fn(),
  warn: vi.fn(),
  info: vi.fn(),
  debug: vi.fn(),
}));

vi.mock('~/lib/logger', () => ({ getLogger: () => log }));

vi.mock('~/components/api/eventsAPI', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/eventsAPI')>()),
  downloadSignupRecordsCsv: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

function httpError(status: number, data: unknown) {
  return Object.assign(new Error(`HTTP ${status}`), {
    isAxiosError: true,
    response: { status, data },
  });
}

let clicked: { href: string; download: string }[] = [];
let consoleSpies: ReturnType<typeof vi.spyOn>[] = [];

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 10, 27, 12, 0));
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    writable: true,
    value: vi.fn(() => 'blob:records'),
  });
  Object.defineProperty(URL, 'revokeObjectURL', {
    configurable: true,
    writable: true,
    value: vi.fn(),
  });
  clicked = [];
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    clicked.push({ href: this.href, download: this.download });
  });
  consoleSpies = [
    vi.spyOn(console, 'error'),
    vi.spyOn(console, 'warn'),
    vi.spyOn(console, 'log'),
  ];
});

afterEach(() => {
  for (const spy of consoleSpies) {
    expect(spy).not.toHaveBeenCalled();
  }
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>{ui}</TooltipProvider>
    </QueryClientProvider>,
  );
}

function renderDialog() {
  const onOpenChange = vi.fn();
  renderWithClient(
    <ExportSignupRecordsDialog orgId={7} open onOpenChange={onOpenChange} />,
  );
  return { onOpenChange };
}

describe('ExportSignupRecordsDialog', () => {
  it('defaults to the last 90 days', () => {
    renderDialog();
    expect(screen.getByTestId('export-signup-records-from')).toHaveValue(
      '2026-08-29',
    );
    expect(screen.getByTestId('export-signup-records-to')).toHaveValue(
      '2026-11-27',
    );
    expect(
      screen.getByText(/Dates are in the organization's timezone\./),
    ).toBeInTheDocument();
  });

  it('downloads the CSV with an exclusive until and closes', async () => {
    const blob = new Blob(['a,b\n'], { type: 'text/csv' });
    vi.mocked(downloadSignupRecordsCsv).mockResolvedValue({
      blob,
      filename: 'signup-records-7-20261127.csv',
    });
    const { onOpenChange } = renderDialog();
    fireEvent.change(screen.getByTestId('export-signup-records-from'), {
      target: { value: '2026-02-01' },
    });
    fireEvent.change(screen.getByTestId('export-signup-records-to'), {
      target: { value: '2026-02-28' },
    });
    fireEvent.click(screen.getByTestId('export-signup-records-submit'));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(downloadSignupRecordsCsv).toHaveBeenCalledWith(7, {
      since: '2026-02-01',
      until: '2026-03-01',
    });
    expect(URL.createObjectURL).toHaveBeenCalledWith(blob);
    expect(clicked).toEqual([
      { href: 'blob:records', download: 'signup-records-7-20261127.csv' },
    ]);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:records');
    expect(document.querySelector('a[download]')).toBeNull();
  });

  it('shows a validation error and does not request when To is before From', async () => {
    renderDialog();
    fireEvent.change(screen.getByTestId('export-signup-records-from'), {
      target: { value: '2026-03-01' },
    });
    fireEvent.change(screen.getByTestId('export-signup-records-to'), {
      target: { value: '2026-02-01' },
    });
    fireEvent.click(screen.getByTestId('export-signup-records-submit'));
    expect(
      await screen.findByText('To must be on or after From.'),
    ).toBeInTheDocument();
    expect(downloadSignupRecordsCsv).not.toHaveBeenCalled();
  });

  it('disables submit while the download is pending', async () => {
    let resolve: (v: { blob: Blob; filename: string }) => void = () => {};
    vi.mocked(downloadSignupRecordsCsv).mockReturnValue(
      new Promise((r) => {
        resolve = r;
      }),
    );
    const { onOpenChange } = renderDialog();
    fireEvent.click(screen.getByTestId('export-signup-records-submit'));
    await waitFor(() =>
      expect(screen.getByTestId('export-signup-records-submit')).toBeDisabled(),
    );
    resolve({ blob: new Blob(['x']), filename: 'f.csv' });
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it('toasts a shorter-range message for too_many_records', async () => {
    vi.mocked(downloadSignupRecordsCsv).mockRejectedValue(
      httpError(400, {
        detail: 'Too many records; narrow the date range.',
        code: 'too_many_records',
      }),
    );
    const { onOpenChange } = renderDialog();
    fireEvent.click(screen.getByTestId('export-signup-records-submit'));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'Too many records — choose a shorter range.',
      ),
    );
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
    expect(log.error).toHaveBeenCalled();
    expect(clicked).toEqual([]);
  });

  it('toasts the API message for other errors', async () => {
    vi.mocked(downloadSignupRecordsCsv).mockRejectedValue(
      httpError(400, { until: ['Enter a valid date.'] }),
    );
    renderDialog();
    fireEvent.click(screen.getByTestId('export-signup-records-submit'));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Enter a valid date.'),
    );
    expect(log.error).toHaveBeenCalled();
  });

  it('falls back to a generic message when the error has no body', async () => {
    vi.mocked(downloadSignupRecordsCsv).mockRejectedValue(new Error('boom'));
    renderDialog();
    fireEvent.click(screen.getByTestId('export-signup-records-submit'));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'Could not export sign-up records.',
      ),
    );
  });
});

describe('ExportSignupRecordsButton', () => {
  it('opens the dialog', async () => {
    renderWithClient(<ExportSignupRecordsButton orgId={7} />);
    expect(screen.queryByTestId('export-signup-records-from')).toBeNull();
    fireEvent.click(screen.getByTestId('export-signup-records-button'));
    expect(
      await screen.findByTestId('export-signup-records-from'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Export sign-up records' }),
    ).toBeInTheDocument();
  });
});
