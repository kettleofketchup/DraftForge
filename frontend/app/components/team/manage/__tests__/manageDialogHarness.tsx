import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { AxiosError, AxiosHeaders } from 'axios';
import { MemoryRouter } from 'react-router';
import { expect, vi } from 'vitest';

import type {
  ManagedTeam,
  TeamHistoryPage,
} from '~/components/api/teamManagementAPI';
import { TooltipProvider } from '~/components/ui/tooltip';
import {
  TeamManageDialog,
  type TeamManageDialogProps,
} from '../TeamManageDialog';

export const TEAM_ID = 1;
export const TOURNAMENT_PK = 1;
export const ORG_PK = 7;

export function axiosError(status: number, data: unknown): AxiosError {
  const config = { headers: new AxiosHeaders() };
  return new AxiosError('failed', String(status), config, undefined, {
    status,
    statusText: '',
    headers: {},
    config,
    data,
  });
}

export function stubRadix(): void {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

type AxiosMock = {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
};

export function routeGets(
  axiosMock: AxiosMock,
  routes: {
    team?: ManagedTeam | AxiosError;
    org?: unknown;
    search?: unknown[];
    history?: TeamHistoryPage | AxiosError;
  },
): void {
  axiosMock.get.mockImplementation((url: string) => {
    if (url === `/teams/${TEAM_ID}/history/` && routes.history) {
      return routes.history instanceof AxiosError
        ? Promise.reject(routes.history)
        : Promise.resolve({ data: routes.history });
    }
    if (url === '/users/search/' && routes.search) {
      return Promise.resolve({ data: routes.search });
    }
    if (url === `/teams/${TEAM_ID}/`) {
      return routes.team instanceof AxiosError
        ? Promise.reject(routes.team)
        : Promise.resolve({ data: routes.team });
    }
    if (url === `/organizations/${ORG_PK}/` && routes.org) {
      return Promise.resolve({ data: routes.org });
    }
    return Promise.reject(axiosError(404, {}));
  });
}

export function renderDialog(props: Partial<TeamManageDialogProps> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
  const onOpenChange = vi.fn();
  const onTeamGone = vi.fn();
  const element = (extra: Partial<TeamManageDialogProps> = {}) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <TooltipProvider>
          <TeamManageDialog
            open
            onOpenChange={onOpenChange}
            teamId={TEAM_ID}
            tournamentPk={TOURNAMENT_PK}
            organizationPk={ORG_PK}
            leaguePk={3}
            onTeamGone={onTeamGone}
            {...props}
            {...extra}
          />
        </TooltipProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
  const utils = render(element());
  return {
    ...utils,
    queryClient,
    invalidate,
    onOpenChange,
    onTeamGone,
    rerenderWith: (extra: Partial<TeamManageDialogProps>) =>
      utils.rerender(element(extra)),
  };
}

export const invalidatedKeys = (invalidate: {
  mock: { calls: unknown[][] };
}): unknown[] =>
  invalidate.mock.calls.map(
    (call) => (call[0] as { queryKey: unknown }).queryKey,
  );

/** Opens the reason dialog from a roster row button. */
export async function requestRowAction(
  rowTestId: string,
  label: string,
): Promise<void> {
  const row = await screen.findByTestId(rowTestId);
  fireEvent.click(within(row).getByRole('button', { name: label }));
  await screen.findByTestId('team-action-dialog');
}

/** Radix tabs activate on mouse down, not click. */
export function openTab(testId: string): void {
  fireEvent.mouseDown(screen.getByTestId(testId), { button: 0 });
}

export async function typeReasonAndConfirm(reason: string): Promise<void> {
  fireEvent.change(screen.getByTestId('team-action-reason'), {
    target: { value: reason },
  });
  const confirm = screen.getByTestId('team-action-confirm');
  await waitFor(() => expect(confirm).not.toBeDisabled());
  fireEvent.click(confirm);
}
