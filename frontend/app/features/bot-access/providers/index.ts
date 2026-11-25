import type { FC } from 'react';

import type { BotAccessSnapshot } from '../schemas';
import {
  BASE_NOT_LINKED_MESSAGE,
  BaseBotAccessHelp,
} from './BaseBotAccessHelp';
import {
  DOTA2_NOT_LINKED_MESSAGE,
  Dota2BotAccessHelp,
} from './Dota2BotAccessHelp';

export interface BotAccessProviderCopy {
  Help: FC<{ snapshot: BotAccessSnapshot }>;
  identityLabel: string;
  notLinkedMessage: string;
}

/** Game-specific copy keyed on `snapshot.provider`. Add an entry per supported game. */
export const BOT_ACCESS_PROVIDERS: Record<string, BotAccessProviderCopy> = {
  dota2: {
    Help: Dota2BotAccessHelp,
    identityLabel: 'Steam profile',
    notLinkedMessage: DOTA2_NOT_LINKED_MESSAGE,
  },
};

export const BASE_BOT_ACCESS_PROVIDER: BotAccessProviderCopy = {
  Help: BaseBotAccessHelp,
  identityLabel: 'Profile',
  notLinkedMessage: BASE_NOT_LINKED_MESSAGE,
};

export function getBotAccessProvider(provider: string): BotAccessProviderCopy {
  return Object.hasOwn(BOT_ACCESS_PROVIDERS, provider)
    ? BOT_ACCESS_PROVIDERS[provider]
    : BASE_BOT_ACCESS_PROVIDER;
}
