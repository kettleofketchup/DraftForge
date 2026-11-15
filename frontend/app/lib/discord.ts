import type { DiscordSDK } from '@discord/embedded-app-sdk';
import api from '~/components/api/axios';
import type { UserType } from '~/index';

export interface DraftActivitySession {
  token: string;
  draft_id: number;
  kind: 'hero' | 'team';
  tournament_id: number | null;
  user: UserType;
}

/** These prefixes must also be configured in the Discord Developer Portal. */
export const ACTIVITY_RESOURCE_MAPPINGS = [
  { prefix: '/external/steam', target: 'cdn.cloudflare.steamstatic.com' },
  { prefix: '/external/discord', target: 'cdn.discordapp.com' },
  { prefix: '/external/avatars', target: 'ui-avatars.com' },
];

// Keep one SDK listener per iframe, including after a failed OAuth exchange.
// A real route unmount clears cached credentials; StrictMode's immediate
// remount cancels that reset and shares the handshake already in progress.
let sdk: DiscordSDK | undefined;
let initialization: Promise<DraftActivitySession> | undefined;
let resetTimer: ReturnType<typeof setTimeout> | undefined;
let initializedAt = 0;
const SESSION_CACHE_AGE = 11 * 60 * 60 * 1000;

export function releaseDiscordSession(): void {
  resetTimer = setTimeout(() => {
    initialization = undefined;
    initializedAt = 0;
  }, 0);
}

export function initializeDiscord({
  force = false,
}: { force?: boolean } = {}): Promise<DraftActivitySession> {
  clearTimeout(resetTimer);
  if (
    (force && initializedAt) ||
    (initializedAt && Date.now() - initializedAt > SESSION_CACHE_AGE)
  ) {
    initialization = undefined;
    initializedAt = 0;
  }
  initialization ??= connect().catch((error: unknown) => {
    initialization = undefined;
    throw error;
  });
  return initialization;
}

async function connect(): Promise<DraftActivitySession> {
  if (!new URLSearchParams(window.location.search).has('frame_id')) {
    throw new Error(
      'Launch DraftForge from Discord in a configured voice channel.',
    );
  }
  const { data: config } = await api.get<{
    enabled: boolean;
    client_id: string | null;
  }>('/discord/activity/config/');
  if (!config.enabled || !config.client_id) {
    throw new Error('Discord Activities are unavailable on this server.');
  }
  // Never construct the SDK during SSR or ordinary website navigation.
  if (!sdk) {
    const { DiscordSDK, patchUrlMappings } =
      await import('@discord/embedded-app-sdk');
    sdk = new DiscordSDK(config.client_id);
    // Reused draft components contain absolute image src attributes. Rewrite
    // only those resources; leave website fetch and WebSocket implementations
    // intact. This runs only inside an Activity iframe, once per SDK instance.
    patchUrlMappings(ACTIVITY_RESOURCE_MAPPINGS, {
      patchFetch: false,
      patchWebSocket: false,
      patchXhr: false,
      patchSrcAttributes: true,
    });
  }
  await sdk.ready();
  const { code } = await sdk.commands.authorize({
    client_id: config.client_id,
    response_type: 'code',
    state: '',
    prompt: 'none',
    scope: ['identify'],
  });
  const { data } = await api.post<
    DraftActivitySession & { access_token: string }
  >('/discord/activity/session/', { code, instance_id: sdk.instanceId });
  await sdk.commands.authenticate({ access_token: data.access_token });
  const { access_token: _accessToken, ...session } = data;
  initializedAt = Date.now();
  return session;
}
