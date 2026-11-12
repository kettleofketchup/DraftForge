import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import {
  LeagueStatsResponseSchema,
  type LeagueStatsResponse,
} from "~/features/league-stats/schemas";
import type {
  LeaderboardResponse,
  LeagueStats,
  SortField,
  SortOrder,
} from "./types";

const API_BASE = "/api/steam";

interface LeaderboardParams {
  page?: number;
  pageSize?: number;
  sortBy?: SortField;
  order?: SortOrder;
}

async function fetchLeaderboard(
  params: LeaderboardParams
): Promise<LeaderboardResponse> {
  const searchParams = new URLSearchParams();
  if (params.page) searchParams.set("page", String(params.page));
  if (params.pageSize) searchParams.set("page_size", String(params.pageSize));
  if (params.sortBy) searchParams.set("sort_by", params.sortBy);
  if (params.order) searchParams.set("order", params.order);

  const response = await fetch(`${API_BASE}/leaderboard/?${searchParams}`);
  if (!response.ok) {
    throw new Error("Failed to fetch leaderboard");
  }
  return response.json();
}

async function fetchUserLeagueStats(userId: number, leagueId?: number): Promise<LeagueStats> {
  const params = leagueId ? `?league_id=${leagueId}` : "";
  const response = await fetch(`${API_BASE}/league-stats/${userId}/${params}`);
  if (!response.ok) {
    throw new Error("Failed to fetch league stats");
  }
  return response.json();
}

export class LeagueStatsHttpError extends Error {
  status: number;

  constructor(status: number) {
    super(`Failed to fetch league stats: ${status}`);
    this.name = "LeagueStatsHttpError";
    this.status = status;
  }
}

async function fetchUserLeagueStatsByLeague(
  userId: number,
  leaguePk: number
): Promise<LeagueStatsResponse | null> {
  const response = await fetch(
    `${API_BASE}/league-stats/${userId}/?league=${leaguePk}`
  );
  if (response.status === 404) return null;
  if (!response.ok) throw new LeagueStatsHttpError(response.status);
  return LeagueStatsResponseSchema.parse(await response.json());
}

async function fetchMyLeagueStats(): Promise<LeagueStats> {
  const response = await fetch(`${API_BASE}/league-stats/me/`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error("Failed to fetch league stats");
  }
  return response.json();
}

export function useLeaderboard(params: LeaderboardParams = {}) {
  return useQuery({
    queryKey: ["leaderboard", params],
    queryFn: () => fetchLeaderboard(params),
  });
}

export function useUserLeagueStats(userId: number | null, leagueId?: number) {
  return useQuery({
    queryKey: ["league-stats", userId, leagueId],
    queryFn: () => fetchUserLeagueStats(userId!, leagueId),
    enabled: userId !== null,
  });
}

export function useUserLeagueStatsByLeague(
  userId: number | undefined,
  leaguePk: number | null | undefined
): UseQueryResult<LeagueStatsResponse | null, Error> {
  return useQuery({
    queryKey: ["league-stats", "by-league", userId, leaguePk],
    queryFn: () => fetchUserLeagueStatsByLeague(userId!, leaguePk!),
    enabled: !!userId && !!leaguePk,
    retry: (failureCount, error) =>
      error instanceof LeagueStatsHttpError &&
      error.status !== 404 &&
      failureCount < 1,
  });
}

export function useMyLeagueStats() {
  return useQuery({
    queryKey: ["league-stats", "me"],
    queryFn: fetchMyLeagueStats,
  });
}
