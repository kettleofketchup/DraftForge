import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table";
import { UserPopover } from "~/components/user/UserPopover";
import { cn } from "~/lib/utils";
import type { LeaderboardEntry, SortField, SortOrder } from "./types";

interface LeaderboardTableProps {
  entries: LeaderboardEntry[];
  sortBy: SortField;
  order: SortOrder;
  onSort: (field: SortField) => void;
}

export function LeaderboardTable({
  entries,
  sortBy,
  order,
  onSort,
}: LeaderboardTableProps) {
  const SortableHeader = ({
    field,
    children,
  }: {
    field: SortField;
    children: React.ReactNode;
  }) => (
    <TableHead
      className="cursor-pointer select-none hover:bg-gray-700"
      onClick={() => onSort(field)}
    >
      <div className="flex items-center gap-1">
        {children}
        {sortBy === field && (
          <span className="text-xs">{order === "desc" ? "▼" : "▲"}</span>
        )}
      </div>
    </TableHead>
  );

  return (
    <Table>
      <TableHeader>
        <TableRow className="border-gray-700">
          <TableHead className="w-12">#</TableHead>
          <TableHead>Player</TableHead>
          <SortableHeader field="league_mmr">League MMR</SortableHeader>
          <SortableHeader field="games_played">Games</SortableHeader>
          <SortableHeader field="win_rate">Win Rate</SortableHeader>
          <SortableHeader field="avg_kda">KDA</SortableHeader>
          <TableHead>GPM</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {entries.map((entry, index) => {
          const winRatePercent = Math.round(entry.win_rate * 100);
          const winRateColor =
            winRatePercent >= 55
              ? "text-green-500"
              : winRatePercent <= 45
                ? "text-red-500"
                : "";

          return (
            <TableRow key={entry.user_id} className="border-gray-700">
              <TableCell className="font-medium text-gray-400">
                {index + 1}
              </TableCell>
              <TableCell>
                <UserPopover
                  userId={entry.user_id}
                  username={entry.username}
                  avatar={entry.avatar}
                >
                  <span className="cursor-pointer font-medium hover:underline">
                    {entry.username}
                  </span>
                </UserPopover>
              </TableCell>
              <TableCell>
                <div className="flex items-baseline gap-1">
                  <span className="font-bold">{entry.league_mmr ?? "—"}</span>
                  <span
                    className={cn(
                      "text-xs",
                      entry.mmr_adjustment > 0
                        ? "text-green-500"
                        : entry.mmr_adjustment < 0
                          ? "text-red-500"
                          : "text-gray-500"
                    )}
                  >
                    ({entry.mmr_adjustment > 0 ? "+" : ""}
                    {entry.mmr_adjustment})
                  </span>
                </div>
              </TableCell>
              <TableCell>{entry.games_played}</TableCell>
              <TableCell className={winRateColor}>{winRatePercent}%</TableCell>
              <TableCell>{entry.avg_kda.toFixed(2)}</TableCell>
              <TableCell>{Math.round(entry.avg_gpm)}</TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
