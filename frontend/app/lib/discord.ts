import api from '~/components/api/axios';
import type { UserType } from '~/index';

export interface DraftActivitySession {
  token: string;
  draft_id: number;
  kind: 'hero' | 'team';
  tournament_id: number | null;
  user: UserType;
}

// A single handshake also handles React StrictMode's repeated mount effects.
let initialization: Promise<DraftActivitySession> | undefined;
export function initializeDiscord(): Promise<DraftActivitySession> {
  initialization ??= connect().catch((error: unknown) => {
    initialization = undefined;
    throw error;
  });
  return initialization;
}

async function connect(): Promise<DraftActivitySession> {
  const clientId = import.meta.env.VITE_DISCORD_CLIENT_ID;
  if (
    !clientId ||
    !new URLSearchParams(window.location.search).has('frame_id')
  ) {
    throw new Error(
      'Launch DraftForge from Discord in a configured voice channel.',
    );
  }
  // Never construct the SDK during SSR or ordinary website navigation.
  const { DiscordSDK } = await import('@discord/embedded-app-sdk');
  const sdk = new DiscordSDK(clientId);
  await sdk.ready();
  const { code } = await sdk.commands.authorize({
    client_id: clientId,
    response_type: 'code',
    state: '',
    prompt: 'none',
    scope: ['identify'],
  });
  const { data } = await api.post<
    DraftActivitySession & { access_token: string }
  >('/discord/activity/session/', {
    code,
    instance_id: sdk.instanceId,
  });
  await sdk.commands.authenticate({ access_token: data.access_token });
  const { access_token: _accessToken, ...session } = data;
  return session;
}
