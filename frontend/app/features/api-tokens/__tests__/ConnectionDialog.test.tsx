// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { OrgFeatureAccess } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { ConnectionDialog } from '../ConnectionDialog';
import { listApiTokens } from '../api';
import {
  createConnection,
  getConnection,
  issueConnectionKey,
  revokeConnectionKey,
  updateConnection,
} from '../connectionApi';
import { connectionKeys } from '../connectionQueryKeys';
import type { ApiConnection } from '../connectionSchemas';
import {
  RAW_KEY,
  apiConnection,
  browserStorageText,
  clearBrowserStorage,
  connectionCredential,
} from './connectionFixtures';

vi.mock('../connectionApi', () => ({
  archiveConnection: vi.fn(),
  createConnection: vi.fn(),
  getConnection: vi.fn(),
  getConnectionRun: vi.fn(),
  issueConnectionKey: vi.fn(),
  listConnectionDeliveries: vi.fn(),
  listConnectionRuns: vi.fn(),
  listConnections: vi.fn(),
  revokeConnectionKey: vi.fn(),
  updateConnection: vi.fn(),
}));
vi.mock('../api', () => ({
  createApiToken: vi.fn(),
  getApiLimits: vi.fn(),
  getApiUsage: vi.fn(),
  listApiTokens: vi.fn(),
  putApiLimits: vi.fn(),
  revokeApiToken: vi.fn(),
}));
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

const ORG = 7;
const fullAccess = makeOrgFeatureAccess({
  viewerPk: 9,
  mmrSyncEnabled: true,
  canUseMmrSync: true,
  promotionEnabled: true,
  canUseApiTokens: true,
});
const promotionOnly = makeOrgFeatureAccess({
  viewerPk: 9,
  promotionEnabled: true,
  canUseApiTokens: true,
});

interface Props {
  access?: OrgFeatureAccess;
  orgId?: number;
  connectionId?: number | null;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  onCreated?: (id: number) => void;
  onDirtyChange?: (dirty: boolean) => void;
}

function setup(initial: Props = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const hostSubmit = vi.fn((e: { preventDefault: () => void }) =>
    e.preventDefault(),
  );
  const handlers = {
    onOpenChange: initial.onOpenChange ?? vi.fn(),
    onCreated: initial.onCreated ?? vi.fn(),
    onDirtyChange: initial.onDirtyChange ?? vi.fn(),
  };
  const view = (p: Props): ReactNode => (
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <form onSubmit={hostSubmit} data-testid="host-form">
          <ConnectionDialog
            orgId={p.orgId ?? ORG}
            access={p.access ?? fullAccess}
            connectionId={p.connectionId === undefined ? 12 : p.connectionId}
            open={p.open ?? true}
            {...handlers}
          />
        </form>
      </TooltipProvider>
    </QueryClientProvider>
  );
  let props = initial;
  const result = render(view(props));
  const rerender = (next: Props) => {
    props = { ...props, ...next };
    result.rerender(view(props));
  };
  return { client, hostSubmit, rerender, ...handlers };
}

function cacheText(client: QueryClient): string {
  return JSON.stringify([
    client
      .getQueryCache()
      .getAll()
      .map((q) => [q.queryKey, q.state.data]),
    client
      .getMutationCache()
      .getAll()
      .map((m) => [m.state.data, m.state.variables]),
  ]);
}

function openTab(name: string) {
  const tab = screen.getByTestId(`api-connection-tab-${name}`);
  fireEvent.mouseDown(tab, { button: 0 });
  fireEvent.click(tab);
}

function issuing(row: ApiConnection) {
  vi.mocked(issueConnectionKey).mockImplementation(
    async (_org, _id, _opts, onSecret) => {
      onSecret({ id: 31, prefix: 'feedbeef', token: RAW_KEY });
      return row;
    },
  );
}

beforeEach(() => {
  vi.mocked(listApiTokens).mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  clearBrowserStorage();
});

const keyed = apiConnection({
  inbound_enabled: true,
  operations: ['mmr:read'],
  inbound_credentials: [connectionCredential()],
});

describe('ConnectionDialog', () => {
  it('test_create_save_issue_show_once_rotate_revoke', async () => {
    vi.mocked(createConnection).mockResolvedValue(apiConnection());
    const { client, rerender, onCreated } = setup({ connectionId: null });
    const name = await screen.findByTestId('api-connection-name');
    expect(screen.getByTestId('api-connection-enabled')).toHaveAttribute(
      'aria-checked',
      'false',
    );
    fireEvent.change(name, { target: { value: 'Ratings service' } });
    fireEvent.click(screen.getByTestId('api-connection-save'));
    await waitFor(() =>
      expect(createConnection).toHaveBeenCalledWith(ORG, {
        name: 'Ratings service',
      }),
    );
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(12));

    vi.mocked(getConnection).mockResolvedValue(
      apiConnection({ inbound_enabled: true, operations: ['mmr:read'] }),
    );
    rerender({ connectionId: 12 });
    await screen.findByTestId('api-connection-name');
    openTab('inbound');
    issuing(keyed);
    const issue = await screen.findByTestId('api-connection-key-issue');
    await waitFor(() => expect(issue).toBeEnabled());
    fireEvent.click(issue);
    const secret = await screen.findByTestId('api-connection-key-secret');
    expect(secret).toHaveTextContent(RAW_KEY);
    expect(cacheText(client)).not.toContain(RAW_KEY);
    fireEvent.click(screen.getByText('Done'));
    await waitFor(() =>
      expect(screen.queryByTestId('api-connection-key-secret')).toBeNull(),
    );
    expect(document.body.textContent).not.toContain(RAW_KEY);

    await screen.findByTestId('api-connection-key-prefix');
    fireEvent.click(screen.getByTestId('api-connection-key-rotate'));
    const rotateDialog = await screen.findByRole('alertdialog');
    expect(rotateDialog).toHaveTextContent(/stops working immediately/i);
    fireEvent.click(screen.getByTestId('api-connection-rotate-confirm'));
    await waitFor(() =>
      expect(issueConnectionKey).toHaveBeenLastCalledWith(
        ORG,
        12,
        { rotate: true },
        expect.any(Function),
      ),
    );
    fireEvent.click(await screen.findByText('Done'));

    vi.mocked(revokeConnectionKey).mockResolvedValue(
      apiConnection({ inbound_enabled: true, operations: ['mmr:read'] }),
    );
    fireEvent.click(screen.getByTestId('api-connection-key-revoke'));
    const revokeDialog = await screen.findByRole('alertdialog');
    expect(revokeDialog).toHaveTextContent(/outbound/i);
    fireEvent.click(screen.getByTestId('api-connection-revoke-confirm'));
    await waitFor(() =>
      expect(revokeConnectionKey).toHaveBeenCalledWith(ORG, 12),
    );
    expect(cacheText(client)).not.toContain(RAW_KEY);
    expect(browserStorageText()).not.toContain(RAW_KEY);
  });

  it('test_promotion_only_org_can_manage', async () => {
    vi.mocked(getConnection).mockResolvedValue(apiConnection());
    vi.mocked(updateConnection).mockResolvedValue(
      apiConnection({
        config_version: 2,
        inbound_enabled: true,
        operations: ['promotion:write'],
      }),
    );
    setup({ access: promotionOnly });
    await screen.findByTestId('api-connection-name');
    openTab('inbound');
    expect(screen.getByTestId('api-connection-op-mmr:read')).toBeDisabled();
    expect(
      screen.getByTestId('api-connection-op-mmr:read-locked'),
    ).toHaveTextContent(/locked/i);
    const write = screen.getByTestId('api-connection-op-promotion:write');
    expect(write).toBeEnabled();
    expect(write).toHaveAttribute('aria-checked', 'false');
    fireEvent.click(write);
    fireEvent.click(screen.getByTestId('api-connection-inbound-enabled'));
    expect(screen.getByTestId('api-connection-key-hint')).toHaveTextContent(
      /save/i,
    );
    fireEvent.click(screen.getByTestId('api-connection-save'));
    await waitFor(() =>
      expect(updateConnection).toHaveBeenCalledWith(ORG, 12, {
        config_version: 1,
        inbound_enabled: true,
        operations: ['promotion:write'],
      }),
    );
  });

  it('test_host_form_enter_cannot_submit', async () => {
    vi.mocked(getConnection).mockResolvedValue(apiConnection());
    vi.mocked(updateConnection).mockResolvedValue(
      apiConnection({ config_version: 2, name: 'x' }),
    );
    const { hostSubmit } = setup();
    const dialog = await screen.findByTestId('api-connection-dialog');
    const name = await screen.findByTestId('api-connection-name');
    expect(dialog.querySelector('form')).toBeNull();
    expect(screen.getByTestId('host-form').contains(dialog)).toBe(false);
    fireEvent.change(name, { target: { value: 'x' } });
    const enter = fireEvent.keyDown(name, { key: 'Enter' });
    expect(enter).toBe(false);
    expect(updateConnection).not.toHaveBeenCalled();
    for (const button of within(dialog).getAllByRole('button')) {
      expect(button.getAttribute('type')).toBe('button');
    }
    fireEvent.click(screen.getByTestId('api-connection-save'));
    await waitFor(() => expect(updateConnection).toHaveBeenCalledTimes(1));
    expect(hostSubmit).not.toHaveBeenCalled();
  });

  it('test_secret_cleared_on_close_org_and_viewer_change', async () => {
    vi.mocked(getConnection).mockResolvedValue(
      apiConnection({
        inbound_enabled: true,
        operations: ['mmr:read'],
        outbound_base_url: 'https://ratings.example',
        outbound_auth: 'bearer',
        credential_present: true,
        inbound_credentials: [connectionCredential()],
      }),
    );
    issuing(keyed);
    const { client, rerender, onOpenChange } = setup();
    await screen.findByTestId('api-connection-name');
    expect(
      screen.getByTestId('api-connection-credential-status'),
    ).toHaveTextContent(/stored/i);
    fireEvent.click(screen.getByTestId('api-connection-credential-replace'));
    const credential = screen.getByTestId('api-connection-credential');
    expect(credential).toHaveValue('');
    expect(credential).toHaveAttribute('type', 'password');
    fireEvent.change(credential, { target: { value: 'outbound-secret' } });
    expect(cacheText(client)).not.toContain('outbound-secret');

    fireEvent.click(screen.getByTestId('api-connection-cancel'));
    fireEvent.click(
      await screen.findByTestId('api-connection-discard-confirm'),
    );
    expect(onOpenChange).toHaveBeenCalledWith(false);
    rerender({ open: false });
    await waitFor(() =>
      expect(screen.queryByTestId('api-connection-dialog')).toBeNull(),
    );
    rerender({ open: true });
    await screen.findByTestId('api-connection-name');
    expect(screen.queryByTestId('api-connection-credential')).toBeNull();
    expect(document.body.textContent).not.toContain('outbound-secret');

    openTab('inbound');
    fireEvent.click(await screen.findByTestId('api-connection-key-rotate'));
    fireEvent.click(screen.getByTestId('api-connection-rotate-confirm'));
    await screen.findByTestId('api-connection-key-secret');
    rerender({ access: makeOrgFeatureAccess({ ...fullAccess, viewerPk: 10 }) });
    await waitFor(() =>
      expect(screen.queryByTestId('api-connection-key-secret')).toBeNull(),
    );
    expect(document.body.textContent).not.toContain(RAW_KEY);

    rerender({ access: fullAccess });
    await screen.findByTestId('api-connection-name');
    openTab('inbound');
    fireEvent.click(await screen.findByTestId('api-connection-key-rotate'));
    fireEvent.click(screen.getByTestId('api-connection-rotate-confirm'));
    await screen.findByTestId('api-connection-key-secret');
    rerender({ orgId: ORG + 1 });
    await waitFor(() =>
      expect(screen.queryByTestId('api-connection-key-secret')).toBeNull(),
    );
    expect(document.body.textContent).not.toContain(RAW_KEY);
    expect(cacheText(client)).not.toContain(RAW_KEY);
  });

  it('test_cas_reload_and_dirty_refetch_preserve_draft', async () => {
    const v1 = apiConnection();
    vi.mocked(getConnection).mockResolvedValue(v1);
    const { client, onDirtyChange } = setup();
    const name = await screen.findByTestId('api-connection-name');

    act(() => {
      client.setQueryData(
        connectionKeys.detail(ORG, 9, 12),
        apiConnection({ config_version: 2, name: 'Server rename' }),
      );
    });
    await waitFor(() => expect(name).toHaveValue('Server rename'));
    expect(screen.queryByTestId('api-connection-conflict')).toBeNull();

    fireEvent.change(name, { target: { value: 'My draft' } });
    await waitFor(() => expect(onDirtyChange).toHaveBeenLastCalledWith(true));
    act(() => {
      client.setQueryData(
        connectionKeys.detail(ORG, 9, 12),
        apiConnection({ config_version: 3, name: 'Second rename' }),
      );
    });
    expect(await screen.findByTestId('api-connection-conflict')).toBeVisible();
    expect(name).toHaveValue('My draft');

    vi.mocked(getConnection).mockResolvedValue(
      apiConnection({ config_version: 3, name: 'Second rename' }),
    );
    vi.mocked(updateConnection).mockRejectedValue({
      response: {
        status: 409,
        data: {
          code: 'configuration_changed',
          detail: 'configuration_changed',
        },
      },
    });
    fireEvent.click(screen.getByTestId('api-connection-save'));
    await waitFor(() =>
      expect(updateConnection).toHaveBeenCalledWith(ORG, 12, {
        config_version: 2,
        name: 'My draft',
      }),
    );
    expect(name).toHaveValue('My draft');
    fireEvent.click(screen.getByTestId('api-connection-reload'));
    await waitFor(() => expect(name).toHaveValue('Second rename'));
    expect(screen.queryByTestId('api-connection-conflict')).toBeNull();
    await waitFor(() => expect(onDirtyChange).toHaveBeenLastCalledWith(false));
  });

  it('test_cas_reapply_rebases_draft_onto_latest', async () => {
    vi.mocked(getConnection).mockResolvedValue(apiConnection());
    const { client } = setup();
    const name = await screen.findByTestId('api-connection-name');
    fireEvent.change(name, { target: { value: 'My draft' } });
    const server = apiConnection({
      config_version: 2,
      name: 'Server rename',
      enabled: true,
    });
    act(() => {
      client.setQueryData(connectionKeys.detail(ORG, 9, 12), server);
    });
    await screen.findByTestId('api-connection-conflict');
    fireEvent.click(screen.getByTestId('api-connection-reapply'));
    await waitFor(() =>
      expect(screen.queryByTestId('api-connection-conflict')).toBeNull(),
    );
    expect(name).toHaveValue('My draft');
    expect(screen.getByTestId('api-connection-enabled')).toHaveAttribute(
      'aria-checked',
      'true',
    );
    expect(updateConnection).not.toHaveBeenCalled();
    vi.mocked(updateConnection).mockResolvedValue(
      apiConnection({ config_version: 3, name: 'My draft', enabled: true }),
    );
    fireEvent.click(screen.getByTestId('api-connection-save'));
    await waitFor(() =>
      expect(updateConnection).toHaveBeenCalledWith(ORG, 12, {
        config_version: 2,
        name: 'My draft',
      }),
    );
  });

  it('test_saved_outbound_credential_leaves_no_cache_trace', async () => {
    const stored = apiConnection({
      outbound_base_url: 'https://ratings.example',
      outbound_auth: 'bearer',
      credential_present: true,
    });
    vi.mocked(getConnection).mockResolvedValue(stored);
    vi.mocked(updateConnection).mockResolvedValue(
      apiConnection({ ...stored, config_version: 2 }),
    );
    const { client, rerender } = setup();
    await screen.findByTestId('api-connection-name');
    fireEvent.click(screen.getByTestId('api-connection-credential-replace'));
    fireEvent.change(screen.getByTestId('api-connection-credential'), {
      target: { value: 'outbound-secret' },
    });
    fireEvent.click(screen.getByTestId('api-connection-save'));
    await waitFor(() =>
      expect(updateConnection).toHaveBeenCalledWith(ORG, 12, {
        config_version: 1,
        outbound_credential: 'outbound-secret',
      }),
    );
    await waitFor(() =>
      expect(screen.getByTestId('api-connection-save')).toBeDisabled(),
    );
    expect(cacheText(client)).not.toContain('outbound-secret');
    expect(browserStorageText()).not.toContain('outbound-secret');
    rerender({ open: false });
    await waitFor(() =>
      expect(screen.queryByTestId('api-connection-dialog')).toBeNull(),
    );
    expect(cacheText(client)).not.toContain('outbound-secret');
    expect(browserStorageText()).not.toContain('outbound-secret');
    expect(document.body.textContent).not.toContain('outbound-secret');
  });

  it('shows a mapped server error on the field and no success while pending', async () => {
    vi.mocked(getConnection).mockResolvedValue(
      apiConnection({
        outbound_base_url: 'https://ratings.example',
        outbound_auth: 'bearer',
      }),
    );
    vi.mocked(updateConnection).mockRejectedValue({
      response: {
        status: 400,
        data: { code: 'credential_required', detail: 'credential_required' },
      },
    });
    setup();
    const name = await screen.findByTestId('api-connection-name');
    fireEvent.change(name, { target: { value: 'Renamed' } });
    fireEvent.click(screen.getByTestId('api-connection-save'));
    expect(
      await screen.findByTestId('api-connection-credential-error'),
    ).toHaveTextContent(/credential/i);
  });

  it('closes and drops restricted queries when access is lost', async () => {
    vi.mocked(getConnection).mockResolvedValue(apiConnection());
    const { client, rerender, onOpenChange } = setup();
    await screen.findByTestId('api-connection-name');
    expect(client.getQueryData(connectionKeys.detail(ORG, 9, 12))).toBeTruthy();
    rerender({
      access: makeOrgFeatureAccess({ ...fullAccess, canUseApiTokens: false }),
    });
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(
      client.getQueryData(connectionKeys.detail(ORG, 9, 12)),
    ).toBeUndefined();
    expect(screen.queryByTestId('api-connection-dialog')).toBeNull();
  });
});
