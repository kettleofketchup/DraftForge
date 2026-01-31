import { InfoDialog } from "~/components/ui/dialogs";
import type { HeroDraftRound, DraftTeam } from "./types";
import { getHeroIcon, getHeroName } from "~/lib/dota/heroes";
import { DisplayName } from "~/components/user/avatar";

interface HeroDraftHistoryModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rounds: HeroDraftRound[];
  draftTeams: DraftTeam[];
}

function getRoundIcon(actionType: "ban" | "pick", state: string): string {
  if (state === "planned") return "⏳";
  if (state === "active") return "▶️";
  if (actionType === "ban") return "🚫";
  return "✅";
}

export function HeroDraftHistoryModal({
  open,
  onOpenChange,
  rounds,
  draftTeams,
}: HeroDraftHistoryModalProps) {
  // Get team name by draft_team id
  const getTeamName = (draftTeamId: number): string => {
    const team = draftTeams.find((t) => t.id === draftTeamId);
    return team?.captain ? DisplayName(team.captain) : team?.team_name || "Unknown";
  };

  // Sort rounds by round_number (completed first, then active, then planned)
  const sortedRounds = [...rounds].sort((a, b) => a.round_number - b.round_number);

  return (
    <InfoDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Draft History"
      size="md"
      showClose={false}
    >
      {sortedRounds.length === 0 ? (
        <p className="text-center text-muted-foreground py-8">
          No picks yet
        </p>
      ) : (
        <div className="space-y-2">
          {sortedRounds.map((round) => {
            const heroId = round.hero_id;
            const heroIcon = heroId ? getHeroIcon(heroId) : null;
            const heroName = heroId ? getHeroName(heroId) : "—";
            const isCompleted = round.state === "completed";
            const isActive = round.state === "active";

            return (
              <div
                key={round.id}
                className={`flex items-center gap-3 p-2 rounded-lg ${
                  isActive
                    ? "bg-yellow-500/20 border border-yellow-500/50"
                    : isCompleted
                    ? "bg-muted/50"
                    : "bg-muted/20 opacity-50"
                }`}
              >
                <span className="text-lg w-6 text-center">
                  {getRoundIcon(round.action_type, round.state)}
                </span>
                <div className="flex items-center gap-2 flex-1 min-w-0">
                  {heroIcon && (
                    <img
                      src={heroIcon}
                      alt=""
                      className="w-8 h-8 rounded"
                    />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">
                      {round.action_type === "ban" ? "Ban" : "Pick"}{" "}
                      {round.round_number - 1}: {heroName}
                    </p>
                    <p className="text-xs text-muted-foreground truncate">
                      {getTeamName(round.draft_team)}
                    </p>
                  </div>
                </div>
                <span
                  className={`text-xs px-2 py-0.5 rounded ${
                    round.action_type === "ban"
                      ? "bg-red-500/20 text-red-400"
                      : "bg-green-500/20 text-green-400"
                  }`}
                >
                  {round.action_type}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </InfoDialog>
  );
}
