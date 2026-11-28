// @vitest-environment jsdom
import { zodResolver } from '@hookform/resolvers/zod';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import { useForm, type UseFormReturn } from 'react-hook-form';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { Form } from '~/components/ui/form';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { OrgFeatureAccess } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { ConnectionDialog } from '../ConnectionDialog';
import { ConnectionGeneralTab } from '../ConnectionGeneralTab';
import { ConnectionMmrPullTab } from '../ConnectionMmrPullTab';
import { listApiTokens } from '../api';
import {
  getConnection,
  pullConnection,
  testConnection,
} from '../connectionApi';
import {
  ConnectionFormSchema,
  buildConnectionPatch,
  connectionFormValues,
  type ApiConnection,
  type ConnectionForm,
} from '../connectionSchemas';
import { apiConnection, connectionRun } from './connectionFixtures';

vi.mock('../connectionApi', () => ({
  archiveConnection: vi.fn(),
  createConnection: vi.fn(),
  getConnection: vi.fn(),
  getConnectionRun: vi.fn(),
  getPromotionOutbox: vi.fn(),
  getPromotionStream: vi.fn(),
  issueConnectionKey: vi.fn(),
  listConnectionDeliveries: vi.fn(),
  listConnectionRuns: vi.fn(),
  listConnections: vi.fn(),
  pullConnection: vi.fn(),
  resumeConnectionDeliveries: vi.fn(),
  resumePromotionOutbox: vi.fn(),
  revokeConnectionKey: vi.fn(),
  resyncConnectionDeliveries: vi.fn(),
  sendPromotionBacklog: vi.fn(),
  setPromotionBinding: vi.fn(),
  testConnection: vi.fn(),
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

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
});

beforeEach(() => {
  vi.mocked(testConnection).mockReset();
  vi.mocked(pullConnection).mockReset();
});

const ORG = 7;
const access = makeOrgFeatureAccess({
  viewerPk: 9,
  mmrSyncEnabled: true,
  canUseMmrSync: true,
  promotionEnabled: true,
  canUseApiTokens: true,
});

const savedPull = (overrides: Partial<ApiConnection> = {}): ApiConnection =>
  apiConnection({
    config_version: 3,
    outbound_base_url: 'https://ratings.example',
    ...overrides,
  });

interface HarnessProps {
  saved: ApiConnection | null;
  memberCount?: number | null;
  accessOverride?: OrgFeatureAccess;
  onRunStarted?: (runId: string) => void;
  formRef: { current: UseFormReturn<ConnectionForm> | null };
  tab?: 'pull' | 'general';
}

function Harness({
  saved,
  memberCount = 20,
  accessOverride,
  onRunStarted,
  formRef,
  tab = 'pull',
}: HarnessProps) {
  const form = useForm<ConnectionForm>({
    resolver: zodResolver(ConnectionFormSchema(saved, { memberCount })),
    defaultValues: saved ? connectionFormValues(saved) : undefined,
  });
  formRef.current = form;
  return (
    <Form {...form}>
      {tab === 'pull' ? (
        <ConnectionMmrPullTab
          form={form}
          saved={saved}
          dirty={form.formState.isDirty}
          readOnly={false}
          orgId={ORG}
          access={accessOverride ?? access}
          memberCount={memberCount}
          onRunStarted={onRunStarted}
        />
      ) : (
        <ConnectionGeneralTab form={form} saved={saved} readOnly={false} />
      )}
    </Form>
  );
}

function renderTab(props: Omit<HarnessProps, 'formRef'>) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const formRef: HarnessProps['formRef'] = { current: null };
  const wrap = (node: ReactNode) => (
    <QueryClientProvider client={client}>
      <TooltipProvider>{node}</TooltipProvider>
    </QueryClientProvider>
  );
  const view = render(wrap(<Harness {...props} formRef={formRef} />));
  const form = (): UseFormReturn<ConnectionForm> => {
    if (!formRef.current) throw new Error('form not mounted');
    return formRef.current;
  };
  return { view, form, client };
}

async function validate(form: () => UseFormReturn<ConnectionForm>) {
  let ok = false;
  await act(async () => {
    ok = await form().trigger();
  });
  return ok;
}

describe('ConnectionMmrPullTab', () => {
  it('test_mapping_editor_renders_typed_arrays_and_errors', async () => {
    const saved = savedPull({
      outbound_auth: 'api_key_field',
      credential_present: true,
      mmr_pull_config: {
        ...apiConnection().mmr_pull_config,
        method: 'POST',
        query: { org: '{{org.id}}', limit: 50, k: '{{credential}}' },
        body: { ids: '{{players.steam64_ids}}', live: true },
        credential_field: { location: 'query', key: 'k' },
        mapping: {
          list_path: 'data.players',
          player_id_path: 'steam',
          player_id_type: 'steam64',
          mmr_path: 'rating',
        },
      },
    });
    const { form } = renderTab({ saved });

    const query = screen.getByTestId('api-connection-pull-query');
    expect(within(query).getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByTestId('api-connection-pull-query-key-0')).toHaveValue(
      'org',
    );
    expect(
      screen.getByTestId('api-connection-pull-query-value-0'),
    ).toHaveTextContent('Org ID');
    expect(screen.getByTestId('api-connection-pull-query-value-1')).toHaveValue(
      '50',
    );
    expect(
      screen.getByTestId('api-connection-pull-body-value-0'),
    ).toHaveTextContent('Member Steam64 IDs');
    expect(
      screen.getByTestId('api-connection-pull-credential-key'),
    ).toHaveValue('k');
    expect(screen.getByTestId('api-connection-pull-list_path')).toHaveValue(
      'data.players',
    );
    // No free-form code editor anywhere.
    expect(document.querySelector('textarea')).toBeNull();

    fireEvent.click(
      screen.getByTestId('api-connection-pull-query-chip-steam_account_ids'),
    );
    expect(form().getValues('pull.query')[2]).toEqual({
      key: 'steam_account_ids',
      kind: 'variable',
      value: '{{players.steam_account_ids}}',
    });

    fireEvent.change(screen.getByTestId('api-connection-pull-query-key-1'), {
      target: { value: 'api_key' },
    });
    fireEvent.change(screen.getByTestId('api-connection-pull-mmr_path'), {
      target: { value: 'data..rating' },
    });
    act(() => {
      form().setValue('pull.query.0.value', '{{player.steam64}}');
    });
    expect(await validate(form)).toBe(false);
    expect(await screen.findByText(/looks like a secret/)).toBeInTheDocument();
    expect(
      screen.getAllByText(/dot-separated names and list positions/).length,
    ).toBeGreaterThan(1);
    expect(
      screen.getByText(/One-member variables need the 'Per member'/),
    ).toBeInTheDocument();
  });

  it('shows the page size for cursor paging too', () => {
    const saved = savedPull({
      mmr_pull_config: {
        ...apiConnection().mmr_pull_config,
        pagination: {
          kind: 'cursor',
          start: 1,
          page_size: 200,
          has_more_path: null,
          next_cursor_path: 'meta.next',
        },
      },
    });
    renderTab({ saved });
    expect(screen.getByTestId('api-connection-pull-page-size')).toHaveValue(
      200,
    );
    expect(screen.getByTestId('api-connection-pull-next-cursor')).toHaveValue(
      'meta.next',
    );
    expect(screen.queryByTestId('api-connection-pull-page-start')).toBeNull();
  });

  it('serializes typed rows and the key slot into the saved config', () => {
    const saved = savedPull({
      outbound_auth: 'api_key_field',
      credential_present: true,
    });
    const values = connectionFormValues(saved);
    values.pull.method = 'POST';
    values.pull.body = [
      { key: 'ids', kind: 'variable', value: '{{players.discord_ids}}' },
      { key: 'n', kind: 'number', value: '3' },
    ];
    values.pull.credential_location = 'body';
    values.pull.credential_key = 'key';
    values.interval_minutes = 60;
    const patch = buildConnectionPatch(saved, values);
    expect(patch.interval_minutes).toBe(60);
    expect(patch.mmr_pull_config?.body).toEqual({
      ids: '{{players.discord_ids}}',
      n: 3,
      key: '{{credential}}',
    });
    expect(patch.mmr_pull_config?.credential_field).toEqual({
      location: 'body',
      key: 'key',
    });
    expect(patch.mmr_push_config).toBeUndefined();
  });

  it('test_unsaved_pull_disabled_and_disabled_saved_test_available', async () => {
    vi.mocked(testConnection).mockResolvedValue('run-1');
    const onRunStarted = vi.fn();
    const { form } = renderTab({ saved: savedPull(), onRunStarted });

    const test = screen.getByTestId('api-connection-pull-test');
    const pull = screen.getByTestId('api-connection-pull-now');
    expect(test).toBeEnabled();
    expect(test).toHaveAttribute('type', 'button');
    expect(pull).toBeDisabled();
    expect(
      screen.getByTestId('api-connection-pull-action-reason'),
    ).toHaveTextContent('Turn the connection on and save before pulling.');

    fireEvent.click(test);
    await waitFor(() => expect(onRunStarted).toHaveBeenCalledWith('run-1'));
    expect(testConnection).toHaveBeenCalledWith(ORG, 12, 'mmr_pull');

    act(() => {
      form().setValue('pull.path', '/changed', { shouldDirty: true });
    });
    await waitFor(() =>
      expect(screen.getByTestId('api-connection-pull-test')).toBeDisabled(),
    );
    expect(
      screen.getByTestId('api-connection-pull-action-reason'),
    ).toHaveTextContent('Pulls use the saved configuration');
  });

  it('pulls now only on a saved, enabled pull and reports distinct refusals', async () => {
    vi.mocked(pullConnection).mockResolvedValue(
      connectionRun({ id: 'run-2', state: 'queued' }),
    );
    const onRunStarted = vi.fn();
    renderTab({
      saved: savedPull({ enabled: true, mmr_pull_enabled: true }),
      onRunStarted,
    });
    fireEvent.click(screen.getByTestId('api-connection-pull-now'));
    await waitFor(() => expect(onRunStarted).toHaveBeenCalledWith('run-2'));

    const messages = new Set<string>();
    for (const code of [
      'credential_keys_unavailable',
      'credential_unavailable',
      'rate_limited',
      'configuration_changed',
      'per_member_acknowledgement_required',
    ]) {
      vi.mocked(testConnection).mockRejectedValueOnce({
        response: { data: { code } },
      });
      fireEvent.click(screen.getByTestId('api-connection-pull-test'));
      const error = await screen.findByTestId(
        'api-connection-pull-action-error',
      );
      await waitFor(() => expect(error.textContent).not.toBe(''));
      messages.add(error.textContent ?? '');
      expect(error.textContent).not.toMatch(/Request refused/);
    }
    expect(messages.size).toBe(5);
  });

  it('test_per_member_over_100_requires_ack', async () => {
    const { form, view } = renderTab({ saved: savedPull(), memberCount: 150 });
    expect(screen.queryByTestId('api-connection-pull-ack')).toBeNull();
    expect(
      screen.getByTestId('api-connection-pull-estimate'),
    ).toHaveTextContent('About 1 request per run for 150 members');

    act(() => {
      form().setValue('pull.request_mode', 'per_member', { shouldDirty: true });
    });
    expect(
      await screen.findByTestId('api-connection-pull-ack'),
    ).not.toBeChecked();
    expect(
      screen.getByTestId('api-connection-pull-estimate'),
    ).toHaveTextContent('About 150 requests');
    expect(await validate(form)).toBe(false);
    expect(
      await screen.findByTestId('api-connection-pull-ack-error'),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('api-connection-pull-ack'));
    expect(await validate(form)).toBe(true);
    expect(
      buildConnectionPatch(savedPull(), form().getValues()).mmr_pull_config
        ?.acknowledge_per_member,
    ).toBe(true);

    view.unmount();
    const small = renderTab({ saved: savedPull(), memberCount: 40 });
    act(() => {
      small.form().setValue('pull.request_mode', 'per_member');
    });
    expect(screen.queryByTestId('api-connection-pull-ack')).toBeNull();
    expect(await validate(small.form)).toBe(true);
  });

  it('bounds the schedule and defaults to missing-only, unverified imports', async () => {
    const { form } = renderTab({ saved: savedPull() });
    expect(screen.getByTestId('api-connection-overwrite')).toHaveTextContent(
      'Only fill missing MMRs',
    );
    expect(
      screen.getByTestId('api-connection-mark-verified'),
    ).not.toBeChecked();
    expect(screen.getByTestId('api-connection-schedule')).toHaveTextContent(
      'Manual only',
    );
    for (const [minutes, ok] of [
      [14, false],
      [15, true],
      [10080, true],
      [10081, false],
    ] as const) {
      act(() => {
        form().setValue('interval_minutes', minutes, { shouldDirty: true });
      });
      expect(await validate(form)).toBe(ok);
    }
    expect(screen.getByTestId('api-connection-interval')).toHaveValue(10081);
  });
});

describe('outbound authority', () => {
  it('test_auth_none_shows_authorizer_and_reauthorize', async () => {
    const authorizer = { pk: 44, username: 'night_admin' };
    const { form, view } = renderTab({
      tab: 'general',
      saved: savedPull({
        outbound_auth: 'none',
        outbound_authorizer: 44,
        outbound_principal: authorizer,
        mmr_pull_enabled: true,
      }),
    });
    expect(screen.queryByTestId('api-connection-credential-block')).toBeNull();
    expect(screen.getByTestId('api-connection-authorizer')).toHaveTextContent(
      'Authorized by',
    );
    expect(screen.getByTestId('api-connection-authorizer')).toHaveTextContent(
      'night_admin',
    );
    expect(screen.queryByTestId('api-connection-authority-lost')).toBeNull();
    view.unmount();

    const lost = renderTab({
      tab: 'general',
      saved: savedPull({
        outbound_auth: 'none',
        last_error_code: 'authority_lost',
      }),
    });
    const notice = screen.getByTestId('api-connection-authority-lost');
    expect(notice).toHaveTextContent('no longer manages this organization');
    expect(notice).toHaveTextContent('makes you the authorizer');
    expect(screen.getByTestId('api-connection-authorizer-none')).toBeVisible();
    expect(
      screen.queryByTestId('api-connection-reenable-promotion_push_enabled'),
    ).toBeNull();
    fireEvent.click(
      screen.getByTestId('api-connection-reenable-mmr_pull_enabled'),
    );
    expect(lost.form().getValues('mmr_pull_enabled')).toBe(true);
    expect(lost.form().getFieldState('mmr_pull_enabled').isDirty).toBe(true);
  });

  it('asks for a new credential when a credentialed owner was lost', () => {
    const { form } = renderTab({
      tab: 'general',
      saved: savedPull({
        outbound_auth: 'bearer',
        last_error_code: 'authority_lost',
      }),
    });
    expect(
      screen.getByTestId('api-connection-authority-lost'),
    ).toHaveTextContent('Enter a new credential');
    fireEvent.click(
      screen.getByTestId('api-connection-reenable-mmr_push_enabled'),
    );
    expect(form().getValues('credential_action')).toBe('replace');
    expect(screen.getByTestId('api-connection-credential')).toHaveValue('');
  });
});

describe('dialog integration', () => {
  it('test_keyboard_mobile_and_outer_form_regression', async () => {
    vi.mocked(getConnection).mockResolvedValue(savedPull());
    vi.mocked(listApiTokens).mockResolvedValue([]);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const hostSubmit = vi.fn((e: { preventDefault: () => void }) =>
      e.preventDefault(),
    );
    render(
      <QueryClientProvider client={client}>
        <TooltipProvider>
          <form onSubmit={hostSubmit}>
            <ConnectionDialog
              orgId={ORG}
              access={access}
              connectionId={12}
              open
              onOpenChange={vi.fn()}
              memberCount={150}
            />
          </form>
        </TooltipProvider>
      </QueryClientProvider>,
    );
    const pullTab = await screen.findByTestId('api-connection-tab-pull');
    for (const value of ['push', 'promotion', 'runs', 'recovery']) {
      expect(screen.getByTestId(`api-connection-tab-${value}`)).toBeVisible();
    }
    fireEvent.mouseDown(pullTab);
    fireEvent.click(pullTab);
    const path = await screen.findByTestId('api-connection-pull-path');
    path.focus();
    fireEvent.keyDown(path, { key: 'Enter' });
    expect(hostSubmit).not.toHaveBeenCalled();

    const dialog = screen.getByTestId('api-connection-dialog');
    for (const button of within(dialog).getAllByRole('button')) {
      if (button.closest('[role="tablist"]')) continue;
      expect(button).toHaveAttribute('type', 'button');
    }
    for (const input of within(dialog).getAllByRole('textbox')) {
      expect(
        input.id && document.querySelector(`label[for="${input.id}"]`),
      ).toBeTruthy();
    }
    fireEvent.change(path, { target: { value: '/v2' } });
    expect(screen.getByTestId('api-connection-save')).toBeEnabled();
    expect(hostSubmit).not.toHaveBeenCalled();
  });
});
