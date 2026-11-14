// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { toast } from 'sonner';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import { getOrgFeatures, setOrgFeature } from '../api';
import { PaidFeaturesPanel } from '../PaidFeaturesPanel';
import { orgFeaturesKey } from '../queryKeys';
import type { OrgFeatureRow } from '../schemas';

vi.mock('../api', () => ({ getOrgFeatures: vi.fn(), setOrgFeature: vi.fn() }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// Radix Switch measures its thumb with ResizeObserver, which jsdom lacks.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

const rows: OrgFeatureRow[] = [
  {
    feature: 'contributions',
    enabled: false,
    notes: '',
    enabled_by: null,
    enabled_at: null,
  },
  {
    feature: 'promotion',
    enabled: true,
    notes: 'Paid via invoice 42',
    enabled_by: { pk: 1, username: 'admin' },
    enabled_at: '2026-11-01T12:00:00Z',
  },
];

function setViewer(user: Partial<UserType> | null) {
  useUserStore.setState({ currentUser: (user ?? {}) as UserType });
}

function renderPanel(qc: QueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, ...render(<PaidFeaturesPanel orgId={7} />, { wrapper }) };
}

beforeEach(() => {
  vi.mocked(getOrgFeatures).mockResolvedValue(rows);
});

afterEach(() => {
  cleanup();
  vi.mocked(getOrgFeatures).mockReset();
  vi.mocked(setOrgFeature).mockReset();
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
});

describe('PaidFeaturesPanel', () => {
  it('renders nothing and never fetches for a non-site-admin', async () => {
    setViewer({ pk: 3, username: 'owner', is_staff: false, is_superuser: false });
    const { container } = renderPanel();
    await new Promise((r) => setTimeout(r, 0));
    expect(container).toBeEmptyDOMElement();
    expect(getOrgFeatures).not.toHaveBeenCalled();
  });

  it('renders both rows with notes prefilled for a site admin', async () => {
    setViewer({ pk: 1, username: 'admin', is_staff: true, is_superuser: false });
    renderPanel();
    expect(await screen.findByTestId('paid-features-panel')).toBeInTheDocument();
    const promoNotes = await screen.findByTestId('paid-feature-notes-promotion');
    expect(promoNotes).toHaveValue('Paid via invoice 42');
    expect(screen.getByTestId('paid-feature-notes-contributions')).toHaveValue('');
    expect(screen.getByTestId('paid-feature-switch-promotion')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByTestId('paid-feature-switch-contributions')).toHaveAttribute('aria-checked', 'false');
    expect(getOrgFeatures).toHaveBeenCalledWith(7);
  });

  it('saves a row and invalidates the org and features queries', async () => {
    setViewer({ pk: 1, username: 'admin', is_superuser: true });
    vi.mocked(setOrgFeature).mockResolvedValue(rows);
    const { qc } = renderPanel();
    const invalidate = vi.spyOn(qc, 'invalidateQueries');
    fireEvent.click(await screen.findByTestId('paid-feature-switch-contributions'));
    fireEvent.change(screen.getByTestId('paid-feature-notes-contributions'), {
      target: { value: 'Trial' },
    });
    fireEvent.click(screen.getByTestId('paid-feature-save-contributions'));
    await vi.waitFor(() =>
      expect(setOrgFeature).toHaveBeenCalledWith(7, {
        feature: 'contributions',
        enabled: true,
        notes: 'Trial',
      }),
    );
    await vi.waitFor(() => {
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ['organization', 7] });
      expect(invalidate).toHaveBeenCalledWith({ queryKey: orgFeaturesKey(7) });
    });
    expect(qc.getQueryData(orgFeaturesKey(7))).toEqual(rows);
    expect(toast.success).toHaveBeenCalledWith('Contributions unlocked');
  });

  it('says notes saved when only the notes changed', async () => {
    setViewer({ pk: 1, username: 'admin', is_superuser: true });
    vi.mocked(setOrgFeature).mockResolvedValue(rows);
    renderPanel();
    fireEvent.change(await screen.findByTestId('paid-feature-notes-promotion'), {
      target: { value: 'Renewed' },
    });
    fireEvent.click(screen.getByTestId('paid-feature-save-promotion'));
    await vi.waitFor(() => expect(toast.success).toHaveBeenCalledWith('Promotion notes saved'));
  });

  it('toasts the API error when a save fails', async () => {
    setViewer({ pk: 1, username: 'admin', is_superuser: true });
    vi.mocked(setOrgFeature).mockRejectedValue({ response: { data: { detail: 'x' } } });
    renderPanel();
    fireEvent.click(await screen.findByTestId('paid-feature-save-contributions'));
    await vi.waitFor(() => expect(toast.error).toHaveBeenCalledWith('x'));
  });

  it('shows an inline error when the features fetch fails', async () => {
    setViewer({ pk: 1, username: 'admin', is_superuser: true });
    vi.mocked(getOrgFeatures).mockRejectedValue({ response: { data: { detail: 'Nope' } } });
    renderPanel();
    expect(await screen.findByTestId('paid-features-error')).toHaveTextContent('Nope');
  });
});
