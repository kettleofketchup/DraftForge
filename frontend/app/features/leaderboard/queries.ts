import { useQuery } from "@tanstack/react-query";
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

async function fetchUserLeagueStats(userId: number): Promise<LeagueStats> {
  const response = await fetch(`${API_BASE}/league-stats/${userId}/`);
  if (!response.ok) {
    throw new Error("Failed to fetch league stats");
  }
  return response.json();
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

export function useUserLeagueStats(userId: number | null) {
  return useQuery({
    queryKey: ["league-stats", userId],
    queryFn: () => fetchUserLeagueStats(userId!),
    enabled: userId !== null,
  });
}

export function useMyLeagueStats() {
  return useQuery({
    queryKey: ["league-stats", "me"],
    queryFn: fetchMyLeagueStats,
  });
}
