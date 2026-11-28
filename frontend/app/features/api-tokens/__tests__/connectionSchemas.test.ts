import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  ApiTokenSchema,
  CONNECTION_OPERATIONS,
  ConnectionFormSchema,
  ConnectionPatchSchema,
  ConnectionSchema,
  ConnectionsSchema,
  DeliveryPageSchema,
  IssueKeyResponseSchema,
  RunSchema,
  buildConnectionCreate,
  buildConnectionPatch,
  connectionFormDefaults,
  connectionFormValues,
  operationLabel,
} from '..';
import {
  apiConnection,
  apiConnectionWire,
  connectionCredential,
  connectionRun,
} from './connectionFixtures';

// Written by backend/org/tests/test_api_connections_wire.py from real serializer output.
const backendWire = JSON.parse(
  readFileSync(
    fileURLToPath(
      new URL(
        '../../../../../backend/org/tests/golden/api_connection_wire.json',
        import.meta.url,
      ),
    ),
    'utf8',
  ),
) as {
  connections: unknown[];
  delivery_page: unknown;
  issue_key_response: unknown;
};

describe('backend wire fixture', () => {
  it('parses legacy-route and backfilled rows', () => {
    const rows = ConnectionsSchema.parse(backendWire.connections);
    expect(rows.map((row) => row.name)).toEqual(['Backfilled', 'Legacy route']);
    expect(rows[0].mmr_pull_config.mapping.player_id_type).toBe(
      'steam_account_id',
    );
  });

  it('parses a delivery page with aggregated paused reasons', () => {
    const page = DeliveryPageSchema.parse(backendWire.delivery_page);
    expect(page.reasons.paused).toEqual({ auth_failed: 1, origin_changed: 1 });
  });

  it('parses an issue-key response', () => {
    const parsed = IssueKeyResponseSchema.parse(backendWire.issue_key_response);
    expect(parsed.credential.token).not.toBe('');
  });
});

describe('ConnectionSchema', () => {
  it('parses a wire row and reads an empty run summary as none', () => {
    const parsed = ConnectionSchema.parse(apiConnectionWire());
    expect(parsed.last_run_summary).toBeNull();
    expect(parsed.operations).toEqual([]);
  });

  it('keeps an outbound-only connection with no grants', () => {
    const parsed = ConnectionSchema.parse(
      apiConnectionWire({
        enabled: true,
        mmr_pull_enabled: true,
        outbound_base_url: 'https://ratings.example',
        outbound_auth: 'bearer',
        credential_present: true,
      }),
    );
    expect(parsed.operations).toEqual([]);
    expect(parsed.inbound_enabled).toBe(false);
    expect(parsed.mmr_pull_enabled).toBe(true);
  });

  it('keeps a legacy import-only grant unchanged', () => {
    const parsed = ConnectionSchema.parse(
      apiConnectionWire({
        operations: ['promotion:import'],
        legacy_multi_credential: true,
        inbound_credentials: [
          connectionCredential({ operations: ['promotion:import'] }),
        ],
      }),
    );
    expect(parsed.operations).toEqual(['promotion:import']);
    expect(parsed.inbound_credentials[0].operations).toEqual([
      'promotion:import',
    ]);
    expect(operationLabel('promotion:import')).toMatch(/import/i);
  });

  it('rejects a missing version, an unknown auth mode and a plaintext credential', () => {
    const { config_version: _drop, ...noVersion } = apiConnectionWire();
    expect(ConnectionSchema.safeParse(noVersion).success).toBe(false);
    expect(
      ConnectionSchema.safeParse({
        ...apiConnectionWire(),
        outbound_auth: 'basic',
      }).success,
    ).toBe(false);
    const parsed = ConnectionSchema.parse({
      ...apiConnectionWire(),
      outbound_credential: 'leak',
    });
    expect(parsed).not.toHaveProperty('outbound_credential');
  });

  it('labels every grant, promotion write as receipt import', () => {
    expect(CONNECTION_OPERATIONS.map((op) => op.value)).toEqual([
      'mmr:read',
      'mmr:write',
      'promotion:read',
      'promotion:write',
      'promotion:import',
    ]);
    const write = CONNECTION_OPERATIONS.find(
      (op) => op.value === 'promotion:write',
    );
    expect(write?.description).toMatch(/receipt/i);
  });
});

describe('ApiTokenSchema legacy fallback', () => {
  it('still defaults operation-less legacy rows to the MMR pair', () => {
    const parsed = ApiTokenSchema.parse({
      id: 1,
      name: 'old',
      prefix: 'p',
      user: null,
      created_at: '2026-01-01T00:00:00Z',
      last_used_at: null,
      revoked_at: null,
      revoked_by: null,
    });
    expect(parsed.operations).toEqual(['mmr:read', 'mmr:write']);
  });
});

describe('form defaults and patches', () => {
  it('starts a new connection fully disabled with no grants', () => {
    const defaults = connectionFormDefaults();
    expect(defaults).toMatchObject({
      name: '',
      enabled: false,
      inbound_enabled: false,
      operations: [],
      outbound_base_url: '',
      outbound_auth: 'none',
      credential_action: 'keep',
      outbound_credential: '',
      mmr_push_enabled: false,
      mmr_pull_enabled: false,
      promotion_push_enabled: false,
      game_type: null,
      overwrite_policy: 'missing_only',
      mark_verified: false,
      interval_minutes: null,
    });
    expect(defaults.pull).toMatchObject({
      request_mode: 'org',
      acknowledge_per_member: false,
      query: [],
      body: [],
    });
    expect(buildConnectionCreate(defaults)).toEqual({ name: '' });
  });

  it('round-trips saved sync configs without sending them back', () => {
    const saved = apiConnection({
      config_version: 2,
      outbound_auth: 'api_key_field',
      mmr_pull_config: {
        ...apiConnection().mmr_pull_config,
        method: 'POST',
        query: {
          org: '{{org.id}}',
          limit: 50,
          live: true,
          k: '{{credential}}',
        },
        body: { ids: '{{players.steam64_ids}}', nested: { a: [1] } },
        credential_field: { location: 'query', key: 'k' },
      },
    });
    const values = connectionFormValues(saved);
    expect(values.pull.query.map((r) => r.kind)).toEqual([
      'variable',
      'number',
      'boolean',
    ]);
    expect(values.pull.body[1]).toEqual({
      key: 'nested',
      kind: 'json',
      value: '{"a":[1]}',
    });
    expect(buildConnectionPatch(saved, values)).toEqual({ config_version: 2 });
  });

  it('never seeds the credential input from a saved row', () => {
    const values = connectionFormValues(
      apiConnection({ credential_present: true, outbound_auth: 'bearer' }),
    );
    expect(values.outbound_credential).toBe('');
    expect(values.credential_action).toBe('keep');
  });

  it('sends only changed fields with the saved version', () => {
    const saved = apiConnection({ config_version: 4 });
    const patch = buildConnectionPatch(saved, {
      ...connectionFormValues(saved),
      name: 'Renamed',
      operations: ['mmr:read'],
    });
    expect(patch).toEqual({
      config_version: 4,
      name: 'Renamed',
      operations: ['mmr:read'],
    });
    expect(ConnectionPatchSchema.parse(patch)).toEqual(patch);
  });

  it('sends a replacement credential or an explicit clear, never both', () => {
    const saved = apiConnection({
      outbound_base_url: 'https://ratings.example',
      outbound_auth: 'bearer',
      credential_present: true,
    });
    const base = connectionFormValues(saved);
    expect(
      buildConnectionPatch(saved, {
        ...base,
        credential_action: 'replace',
        outbound_credential: 'new-secret',
      }),
    ).toEqual({ config_version: 1, outbound_credential: 'new-secret' });
    expect(
      buildConnectionPatch(saved, { ...base, credential_action: 'clear' }),
    ).toEqual({ config_version: 1, clear_outbound_credential: true });
    expect(
      ConnectionPatchSchema.safeParse({
        config_version: 1,
        outbound_credential: 'x',
        clear_outbound_credential: true,
      }).success,
    ).toBe(false);
  });

  it('requires a fresh credential when the origin of a stored one changes', () => {
    const saved = apiConnection({
      outbound_base_url: 'https://ratings.example',
      outbound_auth: 'bearer',
      credential_present: true,
    });
    const values = {
      ...connectionFormValues(saved),
      outbound_base_url: 'https://other.example/v1',
    };
    const result = ConnectionFormSchema(saved).safeParse(values);
    expect(result.success).toBe(false);
    expect(
      ConnectionFormSchema(saved).safeParse({
        ...values,
        credential_action: 'clear',
      }).success,
    ).toBe(true);
    expect(
      ConnectionFormSchema(saved).safeParse({
        ...connectionFormValues(saved),
        outbound_base_url: 'https://ratings.example/other-path',
      }).success,
    ).toBe(true);
  });

  it('rejects a non-https destination and an empty replacement', () => {
    const schema = ConnectionFormSchema(null);
    const base = { ...connectionFormDefaults(), name: 'x' };
    expect(
      schema.safeParse({ ...base, outbound_base_url: 'http://a.example' })
        .success,
    ).toBe(false);
    expect(
      schema.safeParse({
        ...base,
        outbound_auth: 'bearer',
        credential_action: 'replace',
      }).success,
    ).toBe(false);
    expect(schema.safeParse({ ...base, name: '  ' }).success).toBe(false);
  });
});

describe('response contracts', () => {
  it('parses an issued key and rejects one without a token', () => {
    const body = {
      connection: apiConnectionWire(),
      credential: { id: 31, prefix: 'feedbeef', token: 'dfk_x' },
    };
    expect(IssueKeyResponseSchema.parse(body).credential.token).toBe('dfk_x');
    expect(
      IssueKeyResponseSchema.safeParse({
        ...body,
        credential: { id: 31, prefix: 'feedbeef' },
      }).success,
    ).toBe(false);
  });

  it('parses runs and rejects an unknown state', () => {
    expect(RunSchema.parse(connectionRun()).state).toBe('succeeded');
    expect(
      RunSchema.safeParse({ ...connectionRun(), state: 'done' }).success,
    ).toBe(false);
  });

  it('parses a delivery page', () => {
    const page = DeliveryPageSchema.parse({
      counts: { pending: 1, retry: 0, paused: 2, in_flight: 0 },
      reasons: { paused: { auth_failed: 2 } },
      items: [
        {
          delivery_id: 'a3b0c442-98fc-4c1c-b39d-5c4f2f0e1a11',
          org_user_id: 5,
          game_type: 1,
          revision: 9,
          state: 'paused',
          attempts: 3,
          due_at: '2026-11-20T10:00:00Z',
          last_reason: 'auth_failed',
          mmr: 4200,
          steam_id: 76561198000000000,
          discord_id: null,
          destination_origin: 'https://ratings.example',
          created_at: '2026-11-20T09:00:00Z',
        },
      ],
      next_cursor: null,
    });
    expect(page.counts.paused).toBe(2);
    expect(page.reasons.paused).toEqual({ auth_failed: 2 });
    expect(
      DeliveryPageSchema.safeParse({ items: [], next_cursor: null }).success,
    ).toBe(false);
  });
});
