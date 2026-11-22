import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { DotaProfileApiSchema, useUserDotaProfile } from '../useUserProfile';

/**
 * These tests use react-dom/server to render the hook synchronously without
 * pulling in @testing-library/react (not a dep of this project). useQuery
 * returns initialData synchronously on first render, which is exactly the
 * behavior we want to verify.
 */

function withQueryClient(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

interface ProbeProps {
  userPk: number | null | undefined;
  orgId: number | null | undefined;
  initialData: Parameters<typeof useUserDotaProfile>[2] extends
    | { initialData?: infer T }
    | undefined
    ? T
    : never;
  onCapture: (snapshot: { data: unknown; isFetching: boolean }) => void;
}

function Probe({ userPk, orgId, initialData, onCapture }: ProbeProps) {
  const result = useUserDotaProfile(userPk, orgId, { initialData });
  onCapture({ data: result.data, isFetching: result.isFetching });
  return null;
}

describe('useUserDotaProfile', () => {
  it('uses initialData when provided', () => {
    const initial = {
      rank_status: 'active',
      rank_medal: 'Legend 1',
      positions: {
        pos_1: true,
        pos_2: false,
        pos_3: false,
        pos_4: false,
        pos_5: false,
      },
      mmr: null,
      battle_cup_tier: null,
      rank_screenshot: null,
      battlecup_screenshot: null,
    };
    let captured: { data: unknown; isFetching: boolean } | null = null;
    renderToStaticMarkup(
      withQueryClient(
        <Probe
          userPk={42}
          orgId={7}
          initialData={initial}
          onCapture={(s) => (captured = s)}
        />,
      ),
    );
    expect(captured).not.toBeNull();
    const snap = captured as unknown as { data: typeof initial };
    expect(snap.data).toBeTruthy();
    expect(snap.data.rank_medal).toBe('Legend 1');
    expect(snap.data.positions.pos_1).toBe(true);
  });

  it('null initialData is coerced to undefined (does not lock query state)', () => {
    let captured: { data: unknown; isFetching: boolean } | null = null;
    renderToStaticMarkup(
      withQueryClient(
        <Probe
          userPk={42}
          orgId={7}
          initialData={null}
          onCapture={(s) => (captured = s)}
        />,
      ),
    );
    // With null coerced to undefined, the query is not seeded with a resolved
    // null state. data should be undefined on first synchronous render (the
    // fetch hasn't resolved yet under SSR), not null.
    expect(captured).not.toBeNull();
    const snap = captured as unknown as { data: unknown };
    expect(snap.data).toBeUndefined();
    expect(snap.data).not.toBeNull();
  });

  it('does not fire query when userPk is null', () => {
    let captured: { data: unknown; isFetching: boolean } | null = null;
    renderToStaticMarkup(
      withQueryClient(
        <Probe
          userPk={null}
          orgId={7}
          initialData={null}
          onCapture={(s) => (captured = s)}
        />,
      ),
    );
    const snap = captured as unknown as { data: unknown; isFetching: boolean };
    expect(snap.isFetching).toBe(false);
  });

  it('does not fire query when orgId is null', () => {
    let captured: { data: unknown; isFetching: boolean } | null = null;
    renderToStaticMarkup(
      withQueryClient(
        <Probe
          userPk={42}
          orgId={null}
          initialData={null}
          onCapture={(s) => (captured = s)}
        />,
      ),
    );
    const snap = captured as unknown as { data: unknown; isFetching: boolean };
    expect(snap.isFetching).toBe(false);
  });
});

describe('DotaProfileApiSchema', () => {
  const body = {
    id: 1,
    org_user_id: 2,
    rank_status: 'never',
    rank_medal: '',
    rank_date: null,
    battle_cup_tier: null,
    mmr: null,
    rank_screenshot: null,
    battlecup_screenshot: null,
    steam_account_id: 4294967295,
    pos_1: false,
    pos_2: false,
    pos_3: false,
    pos_4: false,
    pos_5: false,
  };

  it('parses the user Friend ID, including IDs above 2^31', () => {
    expect(DotaProfileApiSchema.parse(body).steam_account_id).toBe(4294967295);
    expect(
      DotaProfileApiSchema.parse({ ...body, steam_account_id: null })
        .steam_account_id,
    ).toBeNull();
  });

  it('rejects a body without steam_account_id', () => {
    const { steam_account_id: _omit, ...rest } = body;
    expect(() => DotaProfileApiSchema.parse(rest)).toThrow();
  });
});
