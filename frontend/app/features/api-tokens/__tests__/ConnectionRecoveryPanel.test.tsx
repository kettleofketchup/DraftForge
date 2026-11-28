// @vitest-environment jsdom
import { zodResolver } from '@hookform/resolvers/zod';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import { useForm } from 'react-hook-form';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Form } from '~/components/ui/form';
import { TooltipProvider } from '~/components/ui/tooltip';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import {
  ConnectionFormSchema,
  OPERATION_LABELS,
  connectionFormValues,
  type ApiConnection,
  type ConnectionDelivery,
  type ConnectionForm,
  type PromotionOutbox,
  type PromotionStream,
} from '..';
import { ConnectionPromotionTab } from '../ConnectionPromotionTab';
import {
  ConnectionRecoveryPanel,
  PROMOTION_OPERATOR_DOCS,
} from '../ConnectionRecoveryPanel';
import {
  getPromotionOutbox,
  getPromotionStream,
  listConnectionDeliveries,
  resumeConnectionDeliveries,
  resyncConnectionDeliveries,
  sendPromotionBacklog,
  setPromotionBinding,
} from '../connectionApi';
import { apiConnection } from './connectionFixtures';

vi.mock('../connectionApi', () => ({
  getPromotionOutbox: vi.fn(),
  getPromotionStream: vi.fn(),
  listConnectionDeliveries: vi.fn(),
  resumeConnectionDeliveries: vi.fn(),
  resumePromotionOutbox: vi.fn(),
  resyncConnectionDeliveries: vi.fn(),
  sendPromotionBacklog: vi.fn(),
  setPromotionBinding: vi.fn(),
  testConnection: vi.fn(),
}));
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

const ORG = 7;
const access = makeOrgFeatureAccess({
  viewerPk: 9,
  mmrSyncEnabled: true,
  canUseMmrSync: true,
  promotionEnabled: true,
  canUseApiTokens: true,
});

function delivery(overrides: Partial<ConnectionDelivery>): ConnectionDelivery {
  return {
    delivery_id: 'd1',
    org_user_id: 3,
    game_type: 1,
    revision: 4,
    state: 'paused',
    attempts: 1,
    due_at: '2026-11-20T10:00:00Z',
    last_reason: 'auth_failed',
    mmr: 4200,
    steam_id: '1001',
    discord_id: null,
    destination_origin: 'https://ratings.example',
    created_at: '2026-11-20T10:00:00Z',
    ...overrides,
  };
}

function outbox(counts: Partial<PromotionOutbox['counts']>): PromotionOutbox {
  return {
    counts: {
      pending: 0,
      in_flight: 0,
      retry: 0,
      paused: 0,
      backlog_held: 0,
      reconciliation_required: 0,
      applied: 0,
      canceled: 0,
      ...counts,
    },
    reasons: { retry: {}, paused: {}, reconciliation_required: {} },
  };
}

const connection = (overrides: Partial<ApiConnection> = {}): ApiConnection =>
  apiConnection({
    config_version: 5,
    enabled: true,
    mmr_push_enabled: true,
    outbound_base_url: 'https://ratings.example',
    ...overrides,
  });

function wrap(node: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>{node}</TooltipProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listConnectionDeliveries).mockResolvedValue({
    counts: { pending: 0, retry: 0, paused: 0, in_flight: 0 },
    items: [],
    next_cursor: null,
  });
});

describe('ConnectionRecoveryPanel', () => {
  it('test_error_repair_resume_and_origin_resync', async () => {
    vi.mocked(listConnectionDeliveries).mockResolvedValue({
      counts: { pending: 1, retry: 0, paused: 2, in_flight: 0 },
      items: [
        delivery({ delivery_id: 'a', last_reason: 'auth_failed' }),
        delivery({ delivery_id: 'b', last_reason: 'origin_changed' }),
        delivery({ delivery_id: 'c', state: 'pending', last_reason: '' }),
      ],
      next_cursor: null,
    });
    vi.mocked(resumeConnectionDeliveries).mockResolvedValue(1);
    vi.mocked(resyncConnectionDeliveries).mockResolvedValue(12);
    wrap(
      <ConnectionRecoveryPanel
        orgId={ORG}
        access={access}
        connection={connection()}
        readOnly={false}
      />,
    );
    expect(
      await screen.findByTestId('api-connection-delivery-count-paused'),
    ).toHaveTextContent('2');
    const reasons = screen.getByTestId('api-connection-delivery-reasons');
    expect(reasons).toHaveTextContent('rejected the credential');
    expect(reasons).toHaveTextContent('destination changed');
    expect(
      screen.getByTestId('api-connection-origin-resync'),
    ).toHaveTextContent('resync sends');

    fireEvent.click(screen.getByTestId('api-connection-deliveries-resume'));
    await waitFor(() =>
      expect(resumeConnectionDeliveries).toHaveBeenCalledWith(ORG, 12, 5),
    );

    fireEvent.click(screen.getByTestId('api-connection-deliveries-resync'));
    expect(resyncConnectionDeliveries).not.toHaveBeenCalled();
    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent('3 unsent deliveries are canceled');
    expect(dialog).toHaveTextContent('https://ratings.example');
    fireEvent.click(screen.getByTestId('api-connection-resync-confirm'));
    await waitFor(() =>
      expect(resyncConnectionDeliveries).toHaveBeenCalledWith(ORG, 12, 5),
    );
  });

  it('shows a stale-version refusal instead of retrying blindly', async () => {
    vi.mocked(listConnectionDeliveries).mockResolvedValue({
      counts: { pending: 0, retry: 0, paused: 1, in_flight: 0 },
      items: [delivery({})],
      next_cursor: null,
    });
    vi.mocked(resumeConnectionDeliveries).mockRejectedValue({
      response: { data: { code: 'configuration_changed' } },
    });
    wrap(
      <ConnectionRecoveryPanel
        orgId={ORG}
        access={access}
        connection={connection()}
        readOnly={false}
      />,
    );
    fireEvent.click(
      await screen.findByTestId('api-connection-deliveries-resume'),
    );
    expect(
      await screen.findByTestId('api-connection-recovery-error'),
    ).toHaveTextContent('Someone else saved this connection');
    expect(resumeConnectionDeliveries).toHaveBeenCalledTimes(1);
  });

  it('test_backlog_count_confirmation_and_operator_only_reconciliation', async () => {
    vi.mocked(getPromotionOutbox).mockResolvedValue(
      outbox({ backlog_held: 3, reconciliation_required: 2, paused: 0 }),
    );
    vi.mocked(sendPromotionBacklog)
      .mockRejectedValueOnce({
        response: { data: { code: 'backlog_changed' } },
      })
      .mockResolvedValueOnce(3);
    wrap(
      <ConnectionRecoveryPanel
        orgId={ORG}
        access={access}
        connection={connection({ promotion_stream: true })}
        readOnly={false}
      />,
    );
    const send = await screen.findByTestId(
      'api-connection-promotion-send-backlog',
    );
    expect(send).toHaveTextContent('Send backlog (3)');
    expect(
      screen.getByTestId('api-connection-promotion-resume'),
    ).toBeDisabled();

    fireEvent.click(send);
    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent('Send 3 held promotion sends?');
    fireEvent.click(screen.getByTestId('api-connection-backlog-confirm'));
    await waitFor(() =>
      expect(sendPromotionBacklog).toHaveBeenCalledWith(ORG, 12, 3),
    );
    expect(
      await screen.findByTestId('api-connection-recovery-error'),
    ).toHaveTextContent('number of held sends changed');

    const review = screen.getByTestId('api-connection-reconciliation');
    expect(review).toHaveTextContent('2 sends need review by a site operator');
    expect(within(review).getByRole('link')).toHaveAttribute(
      'href',
      PROMOTION_OPERATOR_DOCS,
    );
    expect(within(review).queryByRole('button')).toBeNull();
  });

  it('skips promotion recovery for a connection that is not the stream', async () => {
    wrap(
      <ConnectionRecoveryPanel
        orgId={ORG}
        access={access}
        connection={connection()}
        readOnly={false}
      />,
    );
    await screen.findByTestId('api-connection-delivery-counts');
    expect(getPromotionOutbox).not.toHaveBeenCalled();
    expect(
      screen.queryByTestId('api-connection-promotion-recovery'),
    ).toBeNull();
  });
});

function stream(overrides: Partial<PromotionStream>): PromotionStream {
  return {
    source: 'none',
    adopted: false,
    connection_id: null,
    guild_id: null,
    events: [],
    transport: 'none',
    ...overrides,
  };
}

function PromotionHarness({ saved }: { saved: ApiConnection }) {
  const form = useForm<ConnectionForm>({
    resolver: zodResolver(ConnectionFormSchema(saved)),
    defaultValues: connectionFormValues(saved),
  });
  return (
    <Form {...form}>
      <ConnectionPromotionTab
        form={form}
        saved={saved}
        dirty={false}
        readOnly={false}
        orgId={ORG}
        access={access}
      />
    </Form>
  );
}

describe('ConnectionPromotionTab', () => {
  it('keeps an unadopted deployment stream read-only and labels grants exactly', async () => {
    vi.mocked(getPromotionStream).mockResolvedValue(
      stream({
        source: 'deployment',
        guild_id: '99',
        events: [{ event_id: '5', occasion_id: '7', effective_at: null }],
        transport: 'env',
      }),
    );
    wrap(
      <PromotionHarness
        saved={connection({
          operations: ['promotion:import', 'promotion:read'],
        })}
      />,
    );
    const deployment = await screen.findByTestId(
      'api-connection-promotion-deployment',
    );
    expect(deployment).toHaveTextContent('read-only here');
    expect(deployment).toHaveTextContent('Event 5 → occasion 7');
    expect(screen.queryByTestId('api-connection-promotion-binding')).toBeNull();
    expect(
      screen.getByTestId('api-connection-promotion-push-enabled'),
    ).toBeDisabled();
    expect(
      screen.getByTestId('api-connection-promotion-push-enabled-locked'),
    ).toHaveTextContent("Only the organization's promotion connection");

    const grants = screen.getByTestId('api-connection-promotion-grant-list');
    expect(grants).toHaveTextContent(
      `${OPERATION_LABELS['promotion:read']}: granted`,
    );
    expect(grants).toHaveTextContent(
      `${OPERATION_LABELS['promotion:write']}: not granted`,
    );
    expect(grants).toHaveTextContent(
      `${OPERATION_LABELS['promotion:import']}: granted`,
    );
  });

  it('binds events for the stream with its own explicit save', async () => {
    vi.mocked(getPromotionStream).mockResolvedValue(
      stream({
        source: 'connection',
        adopted: true,
        connection_id: 12,
        transport: 'held',
      }),
    );
    vi.mocked(setPromotionBinding).mockResolvedValue(
      stream({ source: 'connection', adopted: true, connection_id: 12 }),
    );
    wrap(
      <PromotionHarness
        saved={connection({
          promotion_stream: true,
          outbound_auth: 'bearer',
          credential_present: true,
        })}
      />,
    );
    await screen.findByTestId('api-connection-promotion-binding');
    expect(
      screen.getByTestId('api-connection-promotion-push-enabled'),
    ).toBeEnabled();
    fireEvent.click(screen.getByTestId('api-connection-binding-add'));
    fireEvent.change(screen.getByTestId('api-connection-binding-event-0'), {
      target: { value: '5' },
    });
    expect(screen.getByTestId('api-connection-binding-save')).toBeDisabled();
    fireEvent.change(screen.getByTestId('api-connection-binding-occasion-0'), {
      target: { value: '70' },
    });
    fireEvent.click(screen.getByTestId('api-connection-binding-save'));
    await waitFor(() =>
      expect(setPromotionBinding).toHaveBeenCalledWith(ORG, 12, [
        { event_id: '5', occasion_id: '70' },
      ]),
    );
  });
});
