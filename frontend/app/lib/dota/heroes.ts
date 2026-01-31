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
 * Hero aliases for search and display.
 * First alias is the primary short name for display.
 * All aliases are searchable (case-insensitive).
 * Includes: abbreviations, nicknames, legacy DotA 1 names.
 */
const HERO_ALIASES: Record<number, string[]> = {
  // Strength
  102: ['Aba', 'Abaddon'],
  73: ['Alch', 'Alchemist'],
  2: ['Axe'],
  38: ['BM', 'Beast', 'Beastmaster'],
  78: ['Brew', 'Panda', 'Brewmaster'],
  99: ['BB', 'Bristle', 'Bristleback'],
  96: ['Cent', 'Centaur'],
  81: ['CK', 'Chaos'],
  51: ['Clock', 'Clockwerk', 'Rattletrap'],
  135: ['Dawn', 'Dawnbreaker'],
  69: ['Doom', 'Lucifer'],
  49: ['DK', 'Dragon', 'Davion'],
  107: ['Earth', 'ES', 'Kaolin'],
  7: ['Shaker', 'ES', 'Earthshaker', 'Raigor'],
  103: ['ET', 'Elder', 'Titan'],
  59: ['Huskar', 'Husk'],
  23: ['Kunkka', 'Admiral', 'Coco'],
  155: ['Largo'],
  104: ['LC', 'Legion', 'Tresdin'],
  54: ['LS', 'Naix', 'Lifestealer'],
  77: ['Lycan', 'Banehallow'],
  129: ['Mars'],
  60: ['NS', 'Balanar', 'Nightstalker'],
  84: ['Ogre', 'OM'],
  57: ['Omni', 'Omniknight', 'Purist'],
  110: ['Phoenix', 'Icarus'],
  137: ['PB', 'Primal', 'Beast'],
  14: ['Pudge', 'Butcher'],
  28: ['Slardar'],
  71: ['SB', 'Bara', 'Barathrum', 'Spirit Breaker'],
  18: ['Sven', 'Rogue'],
  29: ['Tide', 'Tidehunter', 'Leviathan'],
  98: ['Timber', 'Shredder', 'Rizzrack'],
  19: ['Tiny', 'Stone'],
  83: ['Treant', 'Tree', 'Rooftrellen'],
  100: ['Tusk', 'Ymir'],
  108: ['Underlord', 'Pitlord', 'Abyssal'],
  85: ['Undying', 'Dirge'],
  42: ['WK', 'Leoric', 'Skeleton King', 'SK'],

  // Agility
  1: ['AM', 'Magina', 'Anti-Mage', 'Antimage'],
  4: ['BS', 'Blood', 'Strygwyr', 'Bloodseeker'],
  62: ['BH', 'Gondar', 'Bounty'],
  61: ['Brood', 'BM', 'Broodmother'],
  56: ['Clinkz', 'Bone'],
  6: ['Drow', 'DR', 'Traxex'],
  106: ['Ember', 'Xin'],
  41: ['FV', 'Void', 'Faceless', 'Darkterror'],
  72: ['Gyro', 'Gyrocopter', 'Aurel'],
  123: ['Hood', 'Hoodwink'],
  8: ['Jug', 'Jugg', 'Yurnero', 'Juggernaut'],
  145: ['Kez'],
  80: ['LD', 'Lone', 'Druid', 'Syllabear', 'Sylla'],
  48: ['Luna', 'Moon'],
  94: ['Dusa', 'Medusa'],
  82: ['Meepo', 'Geomancer', 'Geo'],
  9: ['Mirana', 'Potm', 'PotM', 'Priestess'],
  114: ['MK', 'Monkey', 'Wukong'],
  10: ['Morph', 'Morphling'],
  89: ['Naga', 'Slithice'],
  44: ['PA', 'Mortred', 'Phantom'],
  12: ['PL', 'Lancer', 'Azwraith'],
  15: ['Razor', 'Lightning'],
  32: ['Riki', 'Rikimaru', 'SA'],
  11: ['SF', 'Nevermore', 'Shadow Fiend'],
  93: ['Slark', 'Fish'],
  35: ['Sniper', 'Kardel', 'Dwarf'],
  67: ['Spec', 'Spectre', 'Mercurial'],
  46: ['TA', 'Lanaya', 'Templar'],
  109: ['TB', 'Terror', 'Terrorblade'],
  95: ['Troll', 'TW', 'Jah\'rakal'],
  70: ['Ursa', 'Fuzzy', 'Ulfsaar'],
  20: ['VS', 'Venge', 'Shendelzare'],
  47: ['Viper', 'Netherdrake'],
  63: ['Weaver', 'Anub\'seran', 'Bug'],

  // Intelligence
  68: ['AA', 'Apparition', 'Kaldr', 'Ancient'],
  66: ['Chen', 'Holy'],
  5: ['CM', 'Crystal', 'Rylai', 'Maiden'],
  55: ['DS', 'Ish\'kafel', 'Dark Seer'],
  119: ['Willow', 'DW', 'Mireska'],
  87: ['Disruptor', 'Thrall', 'Dis'],
  58: ['Ench', 'Aiushtha', 'Enchantress', 'Deer'],
  121: ['Grim', 'Grimstroke'],
  74: ['Invoker', 'Invo', 'Voker', 'Carl', 'Kael'],
  64: ['Jak', 'Jakiro', 'THD', 'Twin'],
  90: ['KOTL', 'Ezalor', 'Keeper', 'Gandalf'],
  52: ['Lesh', 'Leshrac', 'Disco', 'Pony'],
  31: ['Lich', 'Kel\'Thuzad'],
  25: ['Lina', 'Slayer'],
  26: ['Lion', 'Demon'],
  138: ['Muerta'],
  36: ['Necro', 'Rotund\'jere', 'Necrophos'],
  111: ['Oracle', 'Nerif'],
  76: ['OD', 'Obsidian', 'Harbinger', 'Outworld'],
  13: ['Puck', 'Faerie'],
  45: ['Pugna', 'Oblivion'],
  39: ['QoP', 'Queen', 'Akasha'],
  131: ['RM', 'Ring', 'Ringmaster'],
  86: ['Rubick', 'Grand'],
  79: ['SD', 'Shadow Demon', 'Eredar'],
  27: ['Shaman', 'SS', 'Rhasta', 'Shadow Shaman'],
  75: ['Silencer', 'Nortrom'],
  101: ['Sky', 'Skywrath', 'Dragonus', 'SM'],
  17: ['Storm', 'SS', 'Raijin', 'Storm Spirit'],
  34: ['Tinker', 'Boush'],
  37: ['Warlock', 'Demnok'],
  112: ['WW', 'Wyvern', 'Auroth', 'Winter'],
  30: ['WD', 'Doc', 'Witch', 'Zharvakko'],
  22: ['Zeus', 'Lord'],

  // Universal
  113: ['AW', 'Arc', 'Zet'],
  3: ['Bane', 'Atropos'],
  65: ['Bat', 'Batrider', 'Rider'],
  50: ['Dazzle', 'Shadow'],
  43: ['DP', 'Krobelus', 'Death Prophet'],
  33: ['Enigma', 'Darchrow'],
  91: ['Io', 'Wisp'],
  97: ['Mag', 'Magnus', 'Magnataur'],
  136: ['Marci'],
  53: ['NP', 'Furion', 'Prophet', 'Tequoia', 'Nature'],
  88: ['Nyx', 'NA', 'Anub\'arak'],
  120: ['Pango', 'Pangolier', 'Donté'],
  16: ['SK', 'Sand', 'Crixalis', 'Sand King'],
  128: ['Snap', 'Snapfire', 'Beatrix', 'Grandma'],
  105: ['Techies', 'Squee', 'Spleen', 'Spoon'],
  40: ['Veno', 'Venomancer', 'Lesale'],
  92: ['Visage', 'Necro\'lic'],
  126: ['Void', 'VS', 'Inai', 'Void Spirit'],
  21: ['WR', 'Windrunner', 'Lyralei', 'Windranger'],
};

/**
 * Get the primary short name for a hero (first alias).
 * Falls back to the first word of the localized name if no aliases defined.
 */
export function getHeroShortName(heroId: number): string {
  const aliases = HERO_ALIASES[heroId];
  if (aliases && aliases.length > 0) {
    return aliases[0];
  }

  // Fall back to first word of localized name
  const hero = heroes[heroId];
  if (!hero) return '?';

  const firstWord = hero.localized_name.split(' ')[0];
  return firstWord.length <= 8 ? firstWord : firstWord.substring(0, 6);
}

/**
 * Get all searchable aliases for a hero.
 * Returns array of lowercase strings for matching.
 */
export function getHeroAliases(heroId: number): string[] {
  const aliases = HERO_ALIASES[heroId] || [];
  const hero = heroes[heroId];

  // Combine custom aliases with localized name and internal name
  const allAliases = [...aliases];
  if (hero) {
    allAliases.push(hero.localized_name);
    // Add internal name without prefix (e.g., "antimage" from "npc_dota_hero_antimage")
    const internalName = hero.name.replace('npc_dota_hero_', '');
    allAliases.push(internalName);
  }

  return allAliases.map(a => a.toLowerCase());
}

/**
 * Check if a search query matches a hero by any of its aliases.
 * Case-insensitive partial match.
 */
export function heroMatchesSearch(heroId: number, query: string): boolean {
  if (!query) return true;

  const lowerQuery = query.toLowerCase();
  const aliases = getHeroAliases(heroId);

  return aliases.some(alias => alias.includes(lowerQuery));
}
