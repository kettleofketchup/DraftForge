import { useState } from "react";
import { Button } from "~/components/ui/button";
import { useLeaderboard } from "./queries";
import { LeaderboardTable } from "./LeaderboardTable";
import type { SortField, SortOrder } from "./types";

const PAGE_SIZE = 20;

export function LeaderboardPage() {
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState<SortField>("win_rate");
  const [order, setOrder] = useState<SortOrder>("desc");

  const { data, isLoading, error } = useLeaderboard({
    page,
    pageSize: PAGE_SIZE,
    sortBy,
    order,
  });

  const handleSort = (field: SortField) => {
    if (field === sortBy) {
      setOrder(order === "desc" ? "asc" : "desc");
    } else {
      setSortBy(field);
      setOrder("desc");
    }
    setPage(1);
  };

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="text-gray-400">Loading leaderboard...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="text-red-500">Failed to load leaderboard</div>
      </div>
    );
  }

  return (
    <div className="container mx-auto py-8">
      <h1 className="mb-6 text-3xl font-bold text-white">League Leaderboard</h1>

      <div className="rounded-lg border border-gray-700 bg-gray-800">
        <LeaderboardTable
          entries={data?.results ?? []}
          sortBy={sortBy}
          order={order}
          onSort={handleSort}
          rankOffset={(page - 1) * PAGE_SIZE}
        />
      </div>

      {data && (
        <div className="mt-4 flex items-center justify-between">
          <div className="text-sm text-gray-400">
            Showing {data.results.length} of {data.count} players
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(page - 1)}
              disabled={!data.previous}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(page + 1)}
              disabled={!data.next}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
