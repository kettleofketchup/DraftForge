import { describe, expect, it } from 'vitest';
import { formatDiscordTimestamps } from '../discordPreview';

const EPOCH = 1794704400;
const DATE = new Date(EPOCH * 1000);
const OPTS = { locale: 'en-US', timeZone: 'America/New_York' } as const;
const tz = { timeZone: 'America/New_York' } as const;

function fmt(options: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat('en-US', { ...options, ...tz }).format(DATE);
}

describe('formatDiscordTimestamps', () => {
  it('F reads the full weekday date and time', () => {
    const out = formatDiscordTimestamps(`<t:${EPOCH}:F>`, OPTS);
    expect(out).toBe(
      fmt({
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      }),
    );
    expect(out).toContain('Saturday, November 14, 2026');
    expect(out).toContain('8:00');
    expect(out).toContain('PM');
  });

  it('f reads the date and time without weekday', () => {
    expect(formatDiscordTimestamps(`<t:${EPOCH}:f>`, OPTS)).toBe(
      fmt({
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      }),
    );
  });

  it('D reads the long date', () => {
    const out = formatDiscordTimestamps(`<t:${EPOCH}:D>`, OPTS);
    expect(out).toBe(fmt({ year: 'numeric', month: 'long', day: 'numeric' }));
    expect(out).toBe('November 14, 2026');
  });

  it('d reads the short date', () => {
    const out = formatDiscordTimestamps(`<t:${EPOCH}:d>`, OPTS);
    expect(out).toBe(
      fmt({ year: 'numeric', month: '2-digit', day: '2-digit' }),
    );
    expect(out).toBe('11/14/2026');
  });

  it('t reads the short time', () => {
    expect(formatDiscordTimestamps(`<t:${EPOCH}:t>`, OPTS)).toBe(
      fmt({ hour: 'numeric', minute: '2-digit' }),
    );
  });

  it('T reads the long time', () => {
    expect(formatDiscordTimestamps(`<t:${EPOCH}:T>`, OPTS)).toBe(
      fmt({ hour: 'numeric', minute: '2-digit', second: '2-digit' }),
    );
  });

  it('no style renders as f', () => {
    expect(formatDiscordTimestamps(`<t:${EPOCH}>`, OPTS)).toBe(
      formatDiscordTimestamps(`<t:${EPOCH}:f>`, OPTS),
    );
  });

  it('R reads relative to now in the future', () => {
    const now = new Date((EPOCH - 3 * 86400) * 1000);
    expect(formatDiscordTimestamps(`<t:${EPOCH}:R>`, { ...OPTS, now })).toBe(
      'in 3 days',
    );
  });

  it('R reads relative to now in the past', () => {
    const now = new Date((EPOCH + 2 * 3600) * 1000);
    expect(formatDiscordTimestamps(`<t:${EPOCH}:R>`, { ...OPTS, now })).toBe(
      '2 hours ago',
    );
  });

  it('R picks seconds, minutes, months and years', () => {
    const at = (s: number): string =>
      formatDiscordTimestamps(`<t:${EPOCH}:R>`, {
        ...OPTS,
        now: new Date((EPOCH - s) * 1000),
      });
    expect(at(30)).toBe('in 30 seconds');
    expect(at(5 * 60)).toBe('in 5 minutes');
    expect(at(60 * 86400)).toBe('in 2 months');
    expect(at(2 * 365 * 86400)).toBe('in 2 years');
  });

  it('R moves up a unit when the rounded count reaches the limit', () => {
    const at = (s: number): string =>
      formatDiscordTimestamps(`<t:${EPOCH}:R>`, {
        ...OPTS,
        now: new Date(EPOCH * 1000 - s * 1000),
      });
    expect(at(59.6)).toBe('in 1 minute');
    expect(at(23.6 * 3600)).toBe('in 1 day');
    expect(at(29.6 * 86400)).toBe('in 1 month');
    expect(at(-59.6)).toBe('1 minute ago');
  });

  it('replaces every code and leaves the rest of the text alone', () => {
    const out = formatDiscordTimestamps(
      `On <t:${EPOCH}:D> at <t:${EPOCH}:t>, see you`,
      OPTS,
    );
    expect(out).not.toContain('<t:');
    expect(out).toBe(
      `On November 14, 2026 at ${fmt({ hour: 'numeric', minute: '2-digit' })}, see you`,
    );
  });

  it('leaves malformed codes literal', () => {
    expect(formatDiscordTimestamps('<t:abc:F> <t:123:X> <t:>', OPTS)).toBe(
      '<t:abc:F> <t:123:X> <t:>',
    );
  });

  it('falls back to UTC on an invalid time zone instead of throwing', () => {
    const out = formatDiscordTimestamps(`<t:${EPOCH}:D>`, {
      locale: 'en-US',
      timeZone: 'Not/AZone',
    });
    expect(out).toBe(
      new Intl.DateTimeFormat('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        timeZone: 'UTC',
      }).format(DATE),
    );
  });

  it('falls back to en on an invalid locale instead of throwing', () => {
    const out = formatDiscordTimestamps(`<t:${EPOCH}:F>`, {
      locale: '!!bad',
      timeZone: 'UTC',
    });
    expect(out).toBe(
      new Intl.DateTimeFormat('en', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        timeZone: 'UTC',
      }).format(DATE),
    );
  });
});
