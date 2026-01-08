import { LeaderboardPage } from "~/features/leaderboard";
import type { Route } from "./+types/leaderboard";

export function meta({}: Route.MetaArgs) {
  return [
    { title: "Leaderboard" },
    { name: "description", content: "League leaderboard standings" },
  ];
}

export default function LeaderboardRoute() {
  return <LeaderboardPage />;
}
