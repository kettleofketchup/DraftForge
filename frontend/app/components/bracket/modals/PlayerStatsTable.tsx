// frontend/app/components/bracket/modals/PlayerStatsTable.tsx
import { getHeroIcon, getHeroName } from '~/lib/dota';
import { formatNumber } from '~/lib/dota/utils';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '~/components/ui/table';
import { cn } from '~/lib/utils';
import type { PlayerMatchStats } from '~/lib/dota/schemas';

interface TeamTotals {
  kills: number;
  deaths: number;
  assists: number;
}

interface PlayerStatsTableProps {
  players: PlayerMatchStats[];
  team: 'radiant' | 'dire';
  isWinner: boolean;
  teamTotals?: TeamTotals;
}

export function PlayerStatsTable({
  players,
  team,
  isWinner,
  teamTotals,
}: PlayerStatsTableProps) {
  const totals = teamTotals ?? players.reduce(
    (acc, p) => ({
      kills: acc.kills + p.kills,
      deaths: acc.deaths + p.deaths,
      assists: acc.assists + p.assists,
    }),
    { kills: 0, deaths: 0, assists: 0 }
  );

  const teamLabel = team === 'radiant' ? 'RADIANT' : 'DIRE';

  return (
    <div
      className={cn(
        'rounded-lg overflow-hidden',
        team === 'radiant' ? 'bg-green-950/60' : 'bg-red-950/60'
      )}
    >
      {/* Team Header */}
      <div
        className={cn(
          'flex items-center justify-between px-3 py-2',
          team === 'radiant' ? 'bg-green-900/50' : 'bg-red-900/50'
        )}
      >
        <div className="flex items-center gap-2">
          <span
            className={cn(
              'font-semibold uppercase',
              team === 'radiant' ? 'text-green-400' : 'text-red-400'
            )}
          >
            {teamLabel}
          </span>
          {isWinner && (
            <span className="text-xs bg-green-600 px-1.5 py-0.5 rounded">
              Victory
            </span>
          )}
        </div>
        <span className="text-muted-foreground text-sm">
          {totals.kills} / {totals.deaths} / {totals.assists}
        </span>
      </div>

      <Table>
        <TableHeader>
          <TableRow className="text-xs">
            <TableHead className="w-10">Hero</TableHead>
            <TableHead>Player</TableHead>
            <TableHead className="text-center w-8">K</TableHead>
            <TableHead className="text-center w-8">D</TableHead>
            <TableHead className="text-center w-8">A</TableHead>
            <TableHead className="text-center w-16">LH/DN</TableHead>
            <TableHead className="text-center w-20">GPM/XPM</TableHead>
            <TableHead className="text-right w-16">DMG</TableHead>
            <TableHead className="text-right w-16">BLD</TableHead>
            <TableHead className="text-right w-14">HEAL</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {players.map((player, index) => (
            <TableRow
              key={player.player_slot}
              className={cn(
                'text-sm',
                team === 'radiant'
                  ? index % 2 === 0
                    ? 'bg-green-950/40'
                    : 'bg-green-900/30'
                  : index % 2 === 0
                    ? 'bg-red-950/40'
                    : 'bg-red-900/30'
              )}
            >
              <TableCell className="p-1">
                <img
                  src={getHeroIcon(player.hero_id)}
                  alt={getHeroName(player.hero_id)}
                  className="w-9 h-9 rounded"
                  title={getHeroName(player.hero_id)}
                />
              </TableCell>
              <TableCell className="font-medium">
                {player.username ?? 'Unknown'}
              </TableCell>
              <TableCell className="text-center text-green-400">
                {player.kills}
              </TableCell>
              <TableCell className="text-center text-red-400">
                {player.deaths}
              </TableCell>
              <TableCell className="text-center text-muted-foreground">
                {player.assists}
              </TableCell>
              <TableCell className="text-center">
                {player.last_hits}
                <span className="text-muted-foreground">/</span>
                {player.denies}
              </TableCell>
              <TableCell className="text-center">
                <span className="text-yellow-400">{player.gold_per_min}</span>
                <span className="text-muted-foreground">/</span>
                <span className="text-blue-400">{player.xp_per_min}</span>
              </TableCell>
              <TableCell className="text-right">
                {formatNumber(player.hero_damage)}
              </TableCell>
              <TableCell className="text-right">
                {formatNumber(player.tower_damage)}
              </TableCell>
              <TableCell className="text-right">
                {formatNumber(player.hero_healing)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
