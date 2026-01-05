// Type declarations for dotaconstants
declare module 'dotaconstants/build/heroes.json' {
  interface DotaHeroData {
    id: number;
    name: string;
    localized_name: string;
    img: string;
    icon: string;
    primary_attr: 'str' | 'agi' | 'int' | 'all';
    attack_type: string;
    roles: string[];
    legs: number;
  }

  const heroes: Record<string, DotaHeroData>;
  export default heroes;
}
