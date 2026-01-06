// frontend/app/lib/dota/heroes.ts
import { heroes as heroesData } from 'dotaconstants';

export interface DotaHero {
  id: number;
  name: string;
  localized_name: string;
  img: string;
  icon: string;
  primary_attr: 'str' | 'agi' | 'int' | 'all';
}

export const heroes: Record<string, DotaHero> = heroesData as Record<
  string,
  DotaHero
>;

export function getHero(heroId: number): DotaHero | undefined {
  return heroes[heroId];
}

const STEAM_CDN_BASE = 'https://cdn.cloudflare.steamstatic.com';

export function getHeroIcon(heroId: number): string {
  const icon = heroes[heroId]?.icon;
  if (!icon) return '/placeholder-hero.png';
  // dotaconstants icons are relative paths like /apps/dota2/images/...
  return `${STEAM_CDN_BASE}${icon}`;
}

export function getHeroName(heroId: number): string {
  return heroes[heroId]?.localized_name ?? 'Unknown Hero';
}
