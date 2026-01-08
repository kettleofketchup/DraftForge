export interface LeagueStats {
  user_id: number;
  username: string;
  avatar: string | null;
  base_mmr: number | null;
  league_mmr: number | null;
  league_id: number;
  games_played: number;
  wins: number;
  losses: number;
  win_rate: number;
  avg_kills: number;
  avg_deaths: number;
  avg_assists: number;
  avg_gpm: number;
  avg_xpm: number;
  mmr_adjustment: number;
  last_updated: string;
}

export interface LeaderboardEntry {
  user_id: number;
  username: string;
  avatar: string | null;
  base_mmr: number | null;
  league_mmr: number | null;
  mmr_adjustment: number;
  games_played: number;
  win_rate: number;
  avg_kills: number;
  avg_deaths: number;
  avg_assists: number;
  avg_kda: number;
  avg_gpm: number;
  avg_xpm: number;
}

export interface LeaderboardResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: LeaderboardEntry[];
}

export type SortField = "league_mmr" | "win_rate" | "games_played" | "avg_kda";
export type SortOrder = "asc" | "desc";
