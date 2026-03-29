/** Lightweight types matching backend SSR serializer responses. */

export interface TournamentSSR {
  pk: number;
  name: string;
  org_name: string | null;
  org_logo: string | null;
  league_name: string | null;
}

export interface OrganizationSSR {
  pk: number;
  name: string;
  description: string;
  logo: string;
}

export interface LeagueSSR {
  pk: number;
  name: string;
  description: string;
  org_name: string | null;
  org_logo: string | null;
}

export interface EventSSR {
  id: number;
  name: string;
  description: string;
  org_name: string | null;
  league_name: string | null;
}

export interface HeroDraftSSR {
  pk: number;
  tournament_name: string | null;
  org_name: string | null;
  team_names: string[];
}

export interface UserSSR {
  pk: number;
  username: string;
  nickname: string | null;
  avatar: string | null;
}
