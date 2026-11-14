// Mirror of backend/org/promotion/render.py; render_fixture.json pins parity.

export const PLACEHOLDER_KEYS = [
  'player',
  'promoter',
  'event',
  'event_time',
  'event_time_relative',
  'event_date',
  'signups_open',
  'event_link',
  'org',
  'discord_link',
] as const;

export type PlaceholderKey = (typeof PLACEHOLDER_KEYS)[number];

export interface RenderResult {
  text: string;
  warnings: string[];
}

const TOKEN_RE = new RegExp(`\\{(${PLACEHOLDER_KEYS.join('|')})\\}`, 'g');
const TOKEN_FULL_RE = new RegExp(`^\\{(${PLACEHOLDER_KEYS.join('|')})\\}$`);
const ANY_TOKEN_RE = /\{[^{}]*\}/g;

export const UNBALANCED_BRACE = 'unbalanced brace';

export function scanWarnings(body: string): string[] {
  const warnings: string[] = [];
  for (const match of body.matchAll(ANY_TOKEN_RE)) {
    const token = match[0];
    if (!TOKEN_FULL_RE.test(token)) {
      const warning = `unknown placeholder ${token}`;
      if (!warnings.includes(warning)) warnings.push(warning);
    }
  }
  const leftover = body.replace(ANY_TOKEN_RE, '');
  if (leftover.includes('{') || leftover.includes('}'))
    warnings.push(UNBALANCED_BRACE);
  return warnings;
}

export function renderTemplate(
  body: string,
  ctx: Readonly<Record<string, string>>,
): RenderResult {
  const text = body.replace(TOKEN_RE, (token: string, key: string) =>
    Object.prototype.hasOwnProperty.call(ctx, key) ? ctx[key] : token,
  );
  return { text, warnings: scanWarnings(body) };
}

export interface SampleEvent {
  id: number;
  name: string;
  scheduled_at: string;
  signups_open_at: string | null;
}

export interface SampleOrg {
  name: string;
  discord_link?: string | null;
}

export interface SampleSender {
  username?: string | null;
  nickname?: string | null;
  discordUsername?: string | null;
  discordNickname?: string | null;
  guildNickname?: string | null;
}

export const SAMPLE_PLAYER = 'Player';

export function playerName(user: SampleSender | null | undefined): string {
  if (!user) return '';
  return (
    user.guildNickname ||
    user.discordNickname ||
    user.discordUsername ||
    user.nickname ||
    user.username ||
    ''
  );
}

function discordTimestamp(iso: string, style: string): string {
  return `<t:${Math.floor(new Date(iso).getTime() / 1000)}:${style}>`;
}

function defaultOrigin(): string {
  return typeof window === 'undefined' ? '' : window.location.origin;
}

export function sampleContext(
  event: SampleEvent,
  org: SampleOrg,
  sender: SampleSender | null | undefined,
  origin: string = defaultOrigin(),
): Record<PlaceholderKey, string> {
  return {
    player: SAMPLE_PLAYER,
    promoter: playerName(sender),
    event: event.name,
    event_time: discordTimestamp(event.scheduled_at, 'F'),
    event_time_relative: discordTimestamp(event.scheduled_at, 'R'),
    event_date: discordTimestamp(event.scheduled_at, 'D'),
    signups_open: event.signups_open_at
      ? discordTimestamp(event.signups_open_at, 'R')
      : '',
    event_link: `${origin}/events/${event.id}`,
    org: org.name,
    discord_link: org.discord_link || '',
  };
}
