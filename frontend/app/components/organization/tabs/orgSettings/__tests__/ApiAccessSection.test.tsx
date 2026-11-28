// @vitest-environment jsdom
import { act, render, renderHook } from '@testing-library/react';
import { toast } from 'sonner';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ApiAccessPanelProps } from '~/features/api-tokens/ApiAccessPanel';
import { useApiAccessSection } from '../ApiAccessSection';

const panel = vi.hoisted(() => ({
  props: null as ApiAccessPanelProps | null,
}));

vi.mock('~/features/api-tokens', () => ({
  ApiAccessPanel: (props: ApiAccessPanelProps) => {
    panel.props = props;
    return null;
  },
}));
vi.mock('~/components/organization/hooks/useOrganization', () => ({
  useOrganization: () => ({ organization: undefined }),
}));
vi.mock('sonner', () => ({ toast: { info: vi.fn() } }));

afterEach(() => {
  panel.props = null;
  vi.clearAllMocks();
});

describe('useApiAccessSection', () => {
  it('reports an open connection draft to the host and never saves it', async () => {
    const selectSection = vi.fn();
    const ref = {
      current: { selectSection, sectionOfField: vi.fn(), revealField: vi.fn() },
    };
    const { result } = renderHook(() => useApiAccessSection(7, true, ref));
    render(<>{result.current.content}</>);
    expect(result.current.unit.isDirty).toBe(false);

    const discard = vi.fn();
    act(() => panel.props?.onConnectionDraftChange?.({ dirty: true, discard }));
    expect(result.current.unit.isDirty).toBe(true);

    await expect(result.current.unit.save()).resolves.toBe(false);
    expect(selectSection).toHaveBeenCalledWith('api-access');
    expect(toast.info).toHaveBeenCalled();

    result.current.unit.discard();
    expect(discard).toHaveBeenCalledTimes(1);

    act(() =>
      panel.props?.onConnectionDraftChange?.({ dirty: false, discard }),
    );
    expect(result.current.unit.isDirty).toBe(false);
  });

  it('is never dirty while the section is not enabled', () => {
    const { result } = renderHook(() => useApiAccessSection(7, false));
    render(<>{result.current.content}</>);
    act(() =>
      panel.props?.onConnectionDraftChange?.({
        dirty: true,
        discard: vi.fn(),
      }),
    );
    expect(result.current.unit.isDirty).toBe(false);
  });

  it('remounts the panel and drops an open draft when the org changes', () => {
    const { result, rerender } = renderHook(
      ({ org }: { org: number }) => useApiAccessSection(org, true),
      { initialProps: { org: 7 } },
    );
    const first = result.current.content as { key: string | null };
    render(<>{result.current.content}</>);
    act(() =>
      panel.props?.onConnectionDraftChange?.({
        dirty: true,
        discard: vi.fn(),
      }),
    );
    expect(result.current.unit.isDirty).toBe(true);

    rerender({ org: 8 });
    const second = result.current.content as { key: string | null };
    expect(second.key).not.toBe(first.key);
    expect(result.current.unit.isDirty).toBe(false);
  });
});
