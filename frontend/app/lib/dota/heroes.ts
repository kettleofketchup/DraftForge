// frontend/app/lib/dota/heroes.ts
import heroesData from 'dotaconstants/build/heroes.json';

export interface DotaHero {
  id: number;
  name: string;
  localized_name: string;
  img: string;
  icon: string;
  primary_attr: 'str' | 'agi' | 'int' | 'all';
}

export const heroes: Record<string, DotaHero> = heroesData;

export function getHero(heroId: number): DotaHero | undefined {
  return heroes[heroId];
}

export function getHeroIcon(heroId: number): string {
  return heroes[heroId]?.icon ?? '/placeholder-hero.png';
}

export function getHeroName(heroId: number): string {
  return heroes[heroId]?.localized_name ?? 'Unknown Hero';
}
