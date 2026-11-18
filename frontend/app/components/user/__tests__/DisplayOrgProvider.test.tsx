// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { StrictMode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { useDisplayOrgStore } from '~/store/displayOrgStore';

import { DisplayOrgProvider, useDisplayOrgId } from '../DisplayOrgProvider';

const seen: (number | null)[] = [];

function Probe({ id = 'probe' }: { id?: string }) {
  const org = useDisplayOrgStore.getState().orgId;
  seen.push(org);
  return <span data-testid={id}>{String(org)}</span>;
}

function HookProbe() {
  return <span data-testid="hook">{String(useDisplayOrgId())}</span>;
}

describe('DisplayOrgProvider', () => {
  beforeEach(() => {
    seen.length = 0;
    useDisplayOrgStore.setState({ stack: [], orgId: null });
  });

  it('children see the org on their first render', () => {
    render(
      <DisplayOrgProvider orgId={7}>
        <Probe />
      </DisplayOrgProvider>,
    );
    expect(seen).toEqual([7]);
    expect(screen.getByTestId('probe')).toHaveTextContent('7');
  });

  it('nested providers win and unmount restores the outer org', () => {
    const { rerender } = render(
      <DisplayOrgProvider orgId={1}>
        <DisplayOrgProvider orgId={2}>
          <Probe id="inner" />
        </DisplayOrgProvider>
        <HookProbe />
      </DisplayOrgProvider>,
    );
    expect(screen.getByTestId('inner')).toHaveTextContent('2');
    rerender(
      <DisplayOrgProvider orgId={1}>
        <HookProbe />
      </DisplayOrgProvider>,
    );
    expect(useDisplayOrgStore.getState().orgId).toBe(1);
    expect(screen.getByTestId('hook')).toHaveTextContent('1');
  });

  it('remounts children with the new org when orgId changes', () => {
    const { rerender } = render(
      <DisplayOrgProvider orgId={undefined}>
        <Probe />
      </DisplayOrgProvider>,
    );
    rerender(
      <DisplayOrgProvider orgId={9}>
        <Probe />
      </DisplayOrgProvider>,
    );
    expect(seen).toEqual([null, 9]);
    expect(screen.getByTestId('probe')).toHaveTextContent('9');
  });

  it('clears the stack on unmount, including under StrictMode', () => {
    const { unmount } = render(
      <StrictMode>
        <DisplayOrgProvider orgId={4}>
          <Probe />
        </DisplayOrgProvider>
      </StrictMode>,
    );
    expect(seen.every((o) => o === 4)).toBe(true);
    unmount();
    expect(useDisplayOrgStore.getState().stack).toEqual([]);
    expect(useDisplayOrgStore.getState().orgId).toBeNull();
  });
});
