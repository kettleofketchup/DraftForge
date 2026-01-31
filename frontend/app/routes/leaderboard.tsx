import { LeaderboardPage } from "~/features/leaderboard";
import { generateMeta } from "~/lib/seo";

export function meta() {
  return generateMeta({
    title: "Leaderboard",
    description: "Player rankings and league standings",
    url: "/leaderboard",
  });
}

export default function LeaderboardRoute() {
  return <LeaderboardPage />;
}
