import { z } from 'zod';
import {
  ChatErrorCodeSchema,
  ChatMessageSchema,
  ChatViewerSchema,
  DraftTeamSchema,
  HeroDraftEventSchema,
  HeroDraftRoundSchema,
  HeroDraftSchema,
  HeroDraftTickSchema,
  HeroDraftWebSocketMessageSchema,
} from './schemas';

export type DraftTeam = z.infer<typeof DraftTeamSchema>;
export type HeroDraftRound = z.infer<typeof HeroDraftRoundSchema>;
export type HeroDraft = z.infer<typeof HeroDraftSchema>;
export type HeroDraftTick = z.infer<typeof HeroDraftTickSchema>;
export type HeroDraftEvent = z.infer<typeof HeroDraftEventSchema>;
export type HeroDraftWebSocketMessage = z.infer<
  typeof HeroDraftWebSocketMessageSchema
>;
export type ChatMessage = z.infer<typeof ChatMessageSchema>;
export type ChatViewer = z.infer<typeof ChatViewerSchema>;
export type ChatErrorCode = z.infer<typeof ChatErrorCodeSchema>;
export type PendingChat = { clientMsgId: string; raw: string; sentAt: number };

// Additional utility types
export type HeroDraftState = HeroDraft['state'];
export type DraftRoundAction = HeroDraftRound['action_type'];

// Hero from dotaconstants - type-safe wrapper
export interface DotaHero {
  id: number;
  name: string;
  localized_name: string;
  primary_attr: 'str' | 'agi' | 'int' | 'all';
  attack_type: string;
  roles: string[];
  img: string;
  icon: string;
}
