// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { toast } from 'sonner';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { addOrgPromoter, getOrgPromoters, removeOrgPromoter } from '~/components/api/api';
import type { OrganizationType } from '~/components/organization/schemas';
import type { UserType } from '~/components/user/types';
import { useOrgStore } from '~/store/orgStore';
import { useUserStore } from '~/store/userStore';
import { AdminTeamSection } from '../AdminTeamSection';

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  fetchCurrentUser: vi.fn().mockResolvedValue({ pk: 1, username: 'owner' }),
  getOrgPromoters: vi.fn(),
  addOrgPromoter: vi.fn(),
  removeOrgPromoter: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// Stub the modal: one button per instance that adds user 21 and shows the outcome.
vi.mock('~/components/user/AddUserModal', async () => {
  const { useState } = await import('react');
  return {
    AddUserModal: ({
      title,
      onAdd,
    }: {
      title: string;
      onAdd: (payload: { user_id: number }) => Promise<UserType>;
    }) => {
      const [result, setResult] = useState('');
      const slug = title.split(' ')[1].toLowerCase();
      return (
        <div>
          <button
            type="button"
            data-testid={`stub-add-${slug}`}
            onClick={() =>
              onAdd({ user_id: 21 }).then(
                () => setResult('ok'),
                (err: Error) => setResult(err.message),
              )
            }
          />
          <span data-testid={`stub-result-${slug}`}>{result}</span>
        </div>
      );
    },
  };
});

const owner = { pk: 1, username: 'owner' } as UserType;
const alice = { pk: 21, username: 'alice' } as UserType;
const bob = { pk: 22, username: 'bob' } as UserType;

function makeOrg(overrides: Partial<OrganizationType> = {}): OrganizationType {
  return {
    pk: 7,
    name: 'Org',
    owner,
    admins: [],
    staff: [],
    members_viewer_pk: 1,
    can_manage_promoters: true,
    ...overrides,
  } as OrganizationType;
}

function renderSection(org: OrganizationType) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, ...render(<AdminTeamSection organization={org} />, { wrapper }) };
}

beforeEach(() => {
  useUserStore.setState({ currentUser: owner });
  useOrgStore.setState({ currentOrg: null });
  vi.mocked(getOrgPromoters).mockResolvedValue([alice, bob]);
});

afterEach(() => {
  cleanup();
  vi.mocked(getOrgPromoters).mockReset();
  vi.mocked(addOrgPromoter).mockReset();
  vi.mocked(removeOrgPromoter).mockReset();
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
});

describe('AdminTeamSection promoters', () => {
  it('hides the section and never fetches when the viewer cannot manage promoters', async () => {
    renderSection(makeOrg({ can_manage_promoters: false }));
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByTestId('promoters-section')).not.toBeInTheDocument();
    expect(getOrgPromoters).not.toHaveBeenCalled();
  });

  it('hides the section while the flags belong to another viewer', async () => {
    renderSection(makeOrg({ members_viewer_pk: 99 }));
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByTestId('promoters-section')).not.toBeInTheDocument();
    expect(getOrgPromoters).not.toHaveBeenCalled();
  });

  it('shows the promoter list and add button when the flag is set', async () => {
    renderSection(makeOrg());
    const section = await screen.findByTestId('promoters-section');
    expect(await within(section).findByTestId('team-member-alice')).toBeInTheDocument();
    expect(within(section).getByTestId('team-member-bob')).toBeInTheDocument();
    expect(within(section).getByTestId('add-promoter-btn')).toBeInTheDocument();
    expect(getOrgPromoters).toHaveBeenCalledWith(7);
  });

  it('removes a promoter and refetches the list', async () => {
    vi.mocked(removeOrgPromoter).mockResolvedValue(undefined);
    renderSection(makeOrg());
    fireEvent.click(await screen.findByTestId('remove-promoter-alice'));
    await vi.waitFor(() => expect(removeOrgPromoter).toHaveBeenCalledWith(7, 21));
    await vi.waitFor(() => expect(toast.success).toHaveBeenCalledWith('Promoter removed'));
    await vi.waitFor(() => expect(getOrgPromoters).toHaveBeenCalledTimes(2));
  });

  it('toasts the API error and refetches when the user is no longer a promoter', async () => {
    vi.mocked(removeOrgPromoter).mockRejectedValue({
      response: { status: 400, data: { error: 'not a promoter' } },
    });
    renderSection(makeOrg());
    fireEvent.click(await screen.findByTestId('remove-promoter-bob'));
    await vi.waitFor(() => expect(toast.error).toHaveBeenCalledWith('not a promoter'));
    await vi.waitFor(() => expect(getOrgPromoters).toHaveBeenCalledTimes(2));
  });

  it('adds a promoter and refetches the list', async () => {
    vi.mocked(addOrgPromoter).mockResolvedValue(alice);
    renderSection(makeOrg());
    await screen.findByTestId('promoters-section');
    fireEvent.click(screen.getByTestId('stub-add-promoter'));
    await vi.waitFor(() => expect(addOrgPromoter).toHaveBeenCalledWith(7, 21));
    expect(await screen.findByText('ok')).toBeInTheDocument();
    await vi.waitFor(() => expect(getOrgPromoters).toHaveBeenCalledTimes(2));
  });

  it('rejects with the API message and refetches when the user is already a promoter', async () => {
    vi.mocked(addOrgPromoter).mockRejectedValue({
      response: { status: 400, data: { error: 'already a promoter' } },
    });
    renderSection(makeOrg());
    await screen.findByTestId('promoters-section');
    fireEvent.click(screen.getByTestId('stub-add-promoter'));
    await vi.waitFor(() =>
      expect(screen.getByTestId('stub-result-promoter')).toHaveTextContent('already a promoter'),
    );
    await vi.waitFor(() => expect(getOrgPromoters).toHaveBeenCalledTimes(2));
  });

  it('keeps each row disabled while its own removal is pending', async () => {
    const pending: Array<() => void> = [];
    vi.mocked(removeOrgPromoter).mockImplementation(
      () => new Promise<void>((resolve) => pending.push(resolve)),
    );
    renderSection(makeOrg());
    const removeAlice = await screen.findByTestId('remove-promoter-alice');
    fireEvent.click(removeAlice);
    await vi.waitFor(() => expect(removeAlice).toBeDisabled());
    const removeBob = screen.getByTestId('remove-promoter-bob');
    fireEvent.click(removeBob);
    await vi.waitFor(() => expect(removeBob).toBeDisabled());
    expect(removeAlice).toBeDisabled();
    pending.forEach((resolve) => resolve());
    await vi.waitFor(() => expect(toast.success).toHaveBeenCalledTimes(2));
  });
});
