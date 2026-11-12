import { describe, expect, it } from 'vitest';
import {
  formatWinRate,
  toneChipClass,
  toneClass,
  winRatePercent,
  winRateTone,
} from '../format';

describe('win-rate helpers', () => {
  it.each([
    [0.545, 55, 'good'],
    [0.455, 46, 'neutral'],
    [5 / 11, 45, 'bad'],
    [6 / 11, 55, 'good'],
    [0.55, 55, 'good'],
    [0.596, 60, 'good'],
    [0, 0, 'bad'],
    [1, 100, 'good'],
  ] as const)('%s -> %s%% %s', (rate, pct, tone) => {
    expect(winRatePercent(rate)).toBe(pct);
    expect(winRateTone(rate)).toBe(tone);
  });

  it('formats the rounded percent', () => {
    expect(formatWinRate(0.5714)).toBe('57%');
  });

  it('maps tones to brand classes', () => {
    expect(toneClass).toEqual({
      good: 'text-success',
      bad: 'text-destructive',
      neutral: '',
    });
  });

  it('chip tones swap small red text for a tinted chip', () => {
    expect(toneChipClass.good).toBe('text-success');
    expect(toneChipClass.neutral).toBe('');
    expect(toneChipClass.bad).toContain('bg-destructive/25');
    expect(toneChipClass.bad).toContain('text-foreground');
    expect(toneChipClass.bad).not.toContain('text-destructive');
  });
});
