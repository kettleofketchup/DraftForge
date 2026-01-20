/**
 * Type declarations for dotaconstants package.
 * These types provide type safety when accessing Dota 2 hero data.
 */

declare module 'dotaconstants' {
  export interface DotaHeroData {
    id: number;
    name: string;
    localized_name: string;
    primary_attr: 'str' | 'agi' | 'int' | 'all';
    attack_type: 'Melee' | 'Ranged';
    roles: string[];
    img: string;
    icon: string;
    base_health: number;
    base_health_regen: number;
    base_mana: number;
    base_mana_regen: number;
    base_armor: number;
    base_mr: number;
    base_attack_min: number;
    base_attack_max: number;
    base_str: number;
    base_agi: number;
    base_int: number;
    str_gain: number;
    agi_gain: number;
    int_gain: number;
    attack_range: number;
    projectile_speed: number;
    attack_rate: number;
    base_attack_time: number;
    attack_point: number;
    move_speed: number;
    turn_rate: number | null;
    cm_enabled: boolean;
    legs: number;
    day_vision: number;
    night_vision: number;
  }

  export const heroes: Record<string, DotaHeroData>;
  export const abilities: Record<string, unknown>;
  export const items: Record<string, unknown>;
  export const patchnotes: unknown;
  export const region: Record<string, unknown>;
}
