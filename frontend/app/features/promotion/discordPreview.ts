import { safeTimeZone } from '~/features/contributions/timezone';

export interface DiscordPreviewOptions {
  locale: string;
  timeZone: string;
  now?: Date;
}

const TIMESTAMP_RE = /<t:(-?\d+)(?::([tTdDfFR]))?>/g;

const DATE_LONG: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: 'long',
  day: 'numeric',
};
const TIME_SHORT: Intl.DateTimeFormatOptions = {
  hour: 'numeric',
  minute: '2-digit',
};

const STYLE_OPTIONS: Record<string, Intl.DateTimeFormatOptions> = {
  t: TIME_SHORT,
  T: { ...TIME_SHORT, second: '2-digit' },
  d: { year: 'numeric', month: '2-digit', day: '2-digit' },
  D: DATE_LONG,
  f: { ...DATE_LONG, ...TIME_SHORT },
  F: { weekday: 'long', ...DATE_LONG, ...TIME_SHORT },
};

const RELATIVE_UNITS: ReadonlyArray<
  [Intl.RelativeTimeFormatUnit, number, number]
> = [
  ['second', 1, 60],
  ['minute', 60, 60],
  ['hour', 60 * 60, 24],
  ['day', 24 * 60 * 60, 30],
  ['month', 30 * 24 * 60 * 60, 12],
  ['year', 365 * 24 * 60 * 60, Infinity],
];

function safeLocale(locale: string): string {
  try {
    return Intl.getCanonicalLocales(locale)[0] ?? 'en';
  } catch {
    return 'en';
  }
}

function formatRelative(date: Date, now: Date, locale: string): string {
  const diffSeconds = (date.getTime() - now.getTime()) / 1000;
  const abs = Math.abs(diffSeconds);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'always' });
  const sign = diffSeconds < 0 ? -1 : 1;
  for (const [unit, size, maxCount] of RELATIVE_UNITS) {
    const count = Math.round(abs / size);
    if (count < maxCount) return rtf.format(sign * count, unit);
  }
  return '';
}

export function formatDiscordTimestamps(
  text: string,
  opts: DiscordPreviewOptions,
): string {
  const locale = safeLocale(opts.locale);
  const timeZone = safeTimeZone(opts.timeZone);
  const now = opts.now ?? new Date();
  return text.replace(
    TIMESTAMP_RE,
    (code: string, seconds: string, style: string | undefined) => {
      const date = new Date(Number(seconds) * 1000);
      if (Number.isNaN(date.getTime())) return code;
      if (style === 'R') return formatRelative(date, now, locale);
      return new Intl.DateTimeFormat(locale, {
        ...STYLE_OPTIONS[style ?? 'f'],
        timeZone,
      }).format(date);
    },
  );
}
