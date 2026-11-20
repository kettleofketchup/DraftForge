// @vitest-environment jsdom
import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
} from '@testing-library/react';
import { toast } from 'sonner';
import { describe, expect, it, vi } from 'vitest';

import { type SettingsFormUnit, useSettingsSaveBar } from '../settingsSaveBar';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const unit = (
  id: string,
  over: Partial<SettingsFormUnit> = {},
): SettingsFormUnit => ({
  id,
  isDirty: true,
  save: vi.fn().mockResolvedValue(true),
  discard: vi.fn(),
  ...over,
});

const OPTS = { testIdPrefix: 'x' };

describe('useSettingsSaveBar', () => {
  it('hides the bar when no unit is dirty', () => {
    const { result } = renderHook(() =>
      useSettingsSaveBar([unit('a', { isDirty: false })], OPTS),
    );
    expect(result.current.isDirty).toBe(false);
    expect(result.current.saveBar).toBeNull();
  });

  it('saveAll saves only dirty units in order', async () => {
    const order: string[] = [];
    const mk = (id: string, isDirty: boolean) =>
      unit(id, {
        isDirty,
        save: vi.fn(async () => {
          order.push(id);
          return true;
        }),
      });
    const units = [mk('a', true), mk('b', false), mk('c', true)];
    const { result } = renderHook(() => useSettingsSaveBar(units, OPTS));
    await act(async () => {
      await result.current.saveAll();
    });
    expect(order).toEqual(['a', 'c']);
    expect(units[1].save).not.toHaveBeenCalled();
  });

  it('saveAll continues after a failed unit and skips the success toast', async () => {
    vi.mocked(toast.success).mockClear();
    const units = [
      unit('a', { save: vi.fn().mockResolvedValue(false) }),
      unit('b'),
    ];
    const { result } = renderHook(() => useSettingsSaveBar(units, OPTS));
    let ok = true;
    await act(async () => {
      ok = await result.current.saveAll();
    });
    expect(ok).toBe(false);
    expect(units[1].save).toHaveBeenCalledTimes(1);
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('toasts Settings saved once when all succeed', async () => {
    vi.mocked(toast.success).mockClear();
    const units = [unit('a'), unit('b')];
    const { result } = renderHook(() => useSettingsSaveBar(units, OPTS));
    let ok = false;
    await act(async () => {
      ok = await result.current.saveAll();
    });
    expect(ok).toBe(true);
    expect(toast.success).toHaveBeenCalledTimes(1);
    expect(toast.success).toHaveBeenCalledWith('Settings saved');
  });

  it('discardAll calls discard on every dirty unit', () => {
    const units = [unit('a'), unit('b', { isDirty: false }), unit('c')];
    const { result } = renderHook(() => useSettingsSaveBar(units, OPTS));
    act(() => result.current.discardAll());
    expect(units[0].discard).toHaveBeenCalledTimes(1);
    expect(units[1].discard).not.toHaveBeenCalled();
    expect(units[2].discard).toHaveBeenCalledTimes(1);
  });

  it('Save button shows loading while saving', async () => {
    let release: (v: boolean) => void = () => {};
    const pending = new Promise<boolean>((r) => {
      release = r;
    });
    const units = [unit('a', { save: vi.fn(() => pending) })];
    const Host = () => {
      const { saveBar } = useSettingsSaveBar(units, OPTS);
      return <>{saveBar}</>;
    };
    render(<Host />);
    expect(screen.getByTestId('x-save-bar')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('x-save'));
    expect(screen.getByTestId('x-save')).toBeDisabled();
    expect(screen.getByTestId('x-discard')).toBeDisabled();
    await act(async () => release(true));
    expect(screen.getByTestId('x-save')).not.toBeDisabled();
  });

  it('concurrent saveAll calls share one run', async () => {
    vi.mocked(toast.success).mockClear();
    let release: (v: boolean) => void = () => {};
    const pending = new Promise<boolean>((r) => {
      release = r;
    });
    const units = [unit('a', { save: vi.fn(() => pending) }), unit('b')];
    const { result } = renderHook(() => useSettingsSaveBar(units, OPTS));
    let results: boolean[] = [];
    await act(async () => {
      const first = result.current.saveAll();
      const second = result.current.saveAll();
      release(true);
      results = await Promise.all([first, second]);
    });
    expect(results).toEqual([true, true]);
    expect(units[0].save).toHaveBeenCalledTimes(1);
    expect(units[1].save).toHaveBeenCalledTimes(1);
    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it('a rejecting save counts as failed, later units run, loading clears', async () => {
    vi.mocked(toast.success).mockClear();
    const units = [
      unit('a', { save: vi.fn().mockRejectedValue(new Error('boom')) }),
      unit('b'),
    ];
    const Host = () => {
      const { saveBar, saveAll } = useSettingsSaveBar(units, OPTS);
      return (
        <>
          <button data-testid="go" onClick={() => void saveAll()} />
          {saveBar}
        </>
      );
    };
    render(<Host />);
    await act(async () => {
      fireEvent.click(screen.getByTestId('go'));
    });
    expect(units[1].save).toHaveBeenCalledTimes(1);
    expect(toast.success).not.toHaveBeenCalled();
    expect(screen.getByTestId('x-save')).not.toBeDisabled();
  });

  it('saveAll with no dirty units resolves true without a toast', async () => {
    vi.mocked(toast.success).mockClear();
    const units = [unit('a', { isDirty: false })];
    const { result } = renderHook(() => useSettingsSaveBar(units, OPTS));
    let ok = false;
    await act(async () => {
      ok = await result.current.saveAll();
    });
    expect(ok).toBe(true);
    expect(toast.success).not.toHaveBeenCalled();
  });
});
