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

/**
 * Common short names/abbreviations for Dota 2 heroes.
 * Used for compact display in draft panels, tooltips, etc.
 * Maps hero ID to short name.
 */
const HERO_SHORT_NAMES: Record<number, string> = {
  // Strength
  102: 'Abaddon',
  73: 'Alch',
  2: 'Axe',
  38: 'BM',        // Beastmaster
  78: 'Brew',
  99: 'BB',        // Bristleback
  96: 'Cent',
  81: 'CK',        // Chaos Knight
  51: 'Clock',
  135: 'Dawn',
  69: 'Doom',
  49: 'DK',        // Dragon Knight
  107: 'ES',       // Earth Spirit (context: Earth)
  7: 'Shaker',     // Earthshaker
  103: 'ET',       // Elder Titan
  59: 'Huskar',
  23: 'Kunkka',
  155: 'Largo',
  104: 'LC',       // Legion Commander
  54: 'LS',        // Lifestealer
  77: 'Lycan',
  129: 'Mars',
  60: 'NS',        // Night Stalker
  84: 'Ogre',
  57: 'Omni',
  110: 'Phoenix',
  137: 'PB',       // Primal Beast
  14: 'Pudge',
  28: 'Slardar',
  71: 'SB',        // Spirit Breaker
  18: 'Sven',
  29: 'Tide',
  98: 'Timber',
  19: 'Tiny',
  83: 'Treant',
  100: 'Tusk',
  108: 'Underlord',
  85: 'Undying',
  42: 'WK',        // Wraith King

  // Agility
  1: 'AM',         // Anti-Mage
  4: 'BS',         // Bloodseeker
  62: 'BH',        // Bounty Hunter
  61: 'Brood',
  56: 'Clinkz',
  6: 'Drow',
  106: 'Ember',
  41: 'FV',        // Faceless Void
  72: 'Gyro',
  123: 'Hood',
  8: 'Jug',        // Juggernaut
  145: 'Kez',
  80: 'LD',        // Lone Druid
  48: 'Luna',
  94: 'Dusa',      // Medusa
  82: 'Meepo',
  9: 'Mirana',
  114: 'MK',       // Monkey King
  10: 'Morph',
  89: 'Naga',
  44: 'PA',        // Phantom Assassin
  12: 'PL',        // Phantom Lancer
  15: 'Razor',
  32: 'Riki',
  11: 'SF',        // Shadow Fiend
  93: 'Slark',
  35: 'Sniper',
  67: 'Spec',      // Spectre
  46: 'TA',        // Templar Assassin
  109: 'TB',       // Terrorblade
  95: 'Troll',
  70: 'Ursa',
  20: 'VS',        // Vengeful Spirit
  47: 'Viper',
  63: 'Weaver',

  // Intelligence
  68: 'AA',        // Ancient Apparition
  66: 'Chen',
  5: 'CM',         // Crystal Maiden
  55: 'DS',        // Dark Seer
  119: 'Willow',
  87: 'Disruptor',
  58: 'Ench',
  121: 'Grim',
  74: 'Invoker',
  64: 'Jak',       // Jakiro
  90: 'KOTL',      // Keeper of the Light
  52: 'Lesh',
  31: 'Lich',
  25: 'Lina',
  26: 'Lion',
  138: 'Muerta',
  36: 'Necro',
  111: 'Oracle',
  76: 'OD',        // Outworld Devourer
  13: 'Puck',
  45: 'Pugna',
  39: 'QoP',       // Queen of Pain
  131: 'RM',       // Ring Master
  86: 'Rubick',
  79: 'SD',        // Shadow Demon
  27: 'Shaman',
  75: 'Silencer',
  101: 'Sky',      // Skywrath Mage
  17: 'Storm',
  34: 'Tinker',
  37: 'Warlock',
  112: 'WW',       // Winter Wyvern
  30: 'WD',        // Witch Doctor
  22: 'Zeus',

  // Universal
  113: 'AW',       // Arc Warden
  3: 'Bane',
  65: 'Bat',       // Batrider
  50: 'Dazzle',
  43: 'DP',        // Death Prophet
  33: 'Enigma',
  91: 'Io',
  97: 'Mag',       // Magnus
  136: 'Marci',
  53: 'NP',        // Nature's Prophet (Furion)
  88: 'Nyx',
  120: 'Pango',
  16: 'SK',        // Sand King
  128: 'Snap',
  105: 'Techies',
  40: 'Veno',
  92: 'Visage',
  126: 'Void',     // Void Spirit
  21: 'WR',        // Windranger
};

/**
 * Get the short/abbreviated name for a hero.
 * Falls back to the first word of the localized name if no short name is defined.
 */
export function getHeroShortName(heroId: number): string {
  // Check for custom short name first
  if (HERO_SHORT_NAMES[heroId]) {
    return HERO_SHORT_NAMES[heroId];
  }

  // Fall back to first word of localized name
  const hero = heroes[heroId];
  if (!hero) return '?';

  const localizedName = hero.localized_name;
  const firstWord = localizedName.split(' ')[0];

  // If the first word is short enough, use it
  if (firstWord.length <= 8) {
    return firstWord;
  }

  // Otherwise truncate
  return firstWord.substring(0, 6);
}
