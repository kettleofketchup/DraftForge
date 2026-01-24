import { z } from 'zod';
import {
  DraftTeamSchema,
  HeroDraftRoundSchema,
  HeroDraftSchema,
  HeroDraftTickSchema,
  HeroDraftEventSchema,
  HeroDraftWebSocketMessageSchema,
} from './schemas';

export type DraftTeam = z.infer<typeof DraftTeamSchema>;
export type HeroDraftRound = z.infer<typeof HeroDraftRoundSchema>;
export type HeroDraft = z.infer<typeof HeroDraftSchema>;
export type HeroDraftTick = z.infer<typeof HeroDraftTickSchema>;
export type HeroDraftEvent = z.infer<typeof HeroDraftEventSchema>;
export type HeroDraftWebSocketMessage = z.infer<typeof HeroDraftWebSocketMessageSchema>;

// Additional utility types
export type HeroDraftState = HeroDraft["state"];
export type DraftRoundAction = HeroDraftRound["action_type"];

// Hero from dotaconstants - type-safe wrapper
export interface DotaHero {
  id: number;
  name: string;
  localized_name: string;
  primary_attr: "str" | "agi" | "int" | "all";
  attack_type: string;
  roles: string[];
  img: string;
  icon: string;
}
