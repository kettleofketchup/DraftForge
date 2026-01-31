// frontend/app/components/herodraft/CompletedDraftView.tsx
import { useMemo } from 'react';
import { Avatar, AvatarFallback, AvatarImage } from '~/components/ui/avatar';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { getHeroIcon, getHeroName } from '~/lib/dota/heroes';
import { DisplayName } from '~/components/user/avatar';
import { History } from 'lucide-react';
import type { HeroDraft, DraftTeam, HeroDraftRound } from './types';
import { FastTooltip } from '~/components/ui/tooltip';

interface CompletedDraftViewProps {
  draft: HeroDraft;
  onViewFullDraft?: () => void;
}

interface TeamPicksProps {
  team: DraftTeam;
  picks: HeroDraftRound[];
  side: 'radiant' | 'dire';
}

function TeamPicks({ team, picks, side }: TeamPicksProps) {
  const captain = team.captain;
  const displayName = captain ? DisplayName(captain) : team.team_name;
  const initials = displayName.substring(0, 2).toUpperCase();

  const sideColors = {
    radiant: {
      bg: 'bg-green-900/30',
      border: 'border-green-500/50',
      text: 'text-green-400',
      label: 'Radiant',
    },
    dire: {
      bg: 'bg-red-900/30',
      border: 'border-red-500/50',
      text: 'text-red-400',
      label: 'Dire',
    },
  };

  const colors = sideColors[side];

  return (
    <div
      className={cn(
        'flex flex-col items-center p-4 md:p-6 rounded-lg',
        colors.bg,
        'border',
        colors.border
      )}
      data-testid={`completed-draft-${side}`}
    >
      {/* Team header */}
      <div className="flex flex-col items-center mb-4 md:mb-6">
        <Avatar className="h-16 w-16 md:h-20 md:w-20 mb-2 ring-2 ring-offset-2 ring-offset-gray-900" style={{ ['--tw-ring-color' as string]: side === 'radiant' ? 'rgb(34 197 94)' : 'rgb(239 68 68)' }}>
          <AvatarImage src={captain?.avatarUrl ?? captain?.avatar ?? undefined} />
          <AvatarFallback className="text-lg md:text-xl font-bold">{initials}</AvatarFallback>
        </Avatar>
        <h3 className="text-lg md:text-xl font-bold text-white">{displayName}</h3>
        <span className={cn('text-sm font-medium', colors.text)}>{colors.label}</span>
      </div>

      {/* Hero picks - 5 heroes in a row */}
      <div className="flex flex-wrap justify-center gap-2 md:gap-3">
        {picks.map((round, index) => {
          const heroId = round.hero_id;
          const heroName = heroId ? getHeroName(heroId) : 'Unknown';
          const heroIcon = heroId ? getHeroIcon(heroId) : undefined;

          return (
            <FastTooltip key={round.id} content={heroName} className="text-sm font-medium">
              <div
                className={cn(
                  'size-12 sm:size-14 md:size-16 lg:size-20',
                  'rounded-full bg-gradient-to-b from-slate-600 to-slate-800',
                  'border-2 shadow-lg shadow-black/50',
                  'p-0.5',
                  side === 'radiant' ? 'border-green-500/70' : 'border-red-500/70'
                )}
                data-testid={`completed-draft-${side}-pick-${index}`}
              >
                {heroIcon ? (
                  <img
                    src={heroIcon}
                    alt={heroName}
                    className="size-full rounded-full object-cover"
                  />
                ) : (
                  <div className="size-full rounded-full bg-gray-700 flex items-center justify-center">
                    <span className="text-xs text-gray-400">?</span>
                  </div>
                )}
              </div>
            </FastTooltip>
          );
        })}
      </div>
    </div>
  );
}

export function CompletedDraftView({ draft, onViewFullDraft }: CompletedDraftViewProps) {
  // Find radiant and dire teams
  const { radiantTeam, direTeam, radiantPicks, direPicks } = useMemo(() => {
    const radiant = draft.draft_teams.find((t) => t.is_radiant === true);
    const dire = draft.draft_teams.find((t) => t.is_radiant === false);

    // Get picks (not bans) for each team, sorted by round number
    const radiantPickRounds = draft.rounds
      .filter((r) => r.action_type === 'pick' && r.draft_team === radiant?.id)
      .sort((a, b) => a.round_number - b.round_number);

    const direPickRounds = draft.rounds
      .filter((r) => r.action_type === 'pick' && r.draft_team === dire?.id)
      .sort((a, b) => a.round_number - b.round_number);

    return {
      radiantTeam: radiant,
      direTeam: dire,
      radiantPicks: radiantPickRounds,
      direPicks: direPickRounds,
    };
  }, [draft.draft_teams, draft.rounds]);

  if (!radiantTeam || !direTeam) {
    return (
      <div className="flex-1 flex items-center justify-center" data-testid="completed-draft-error">
        <p className="text-muted-foreground">Draft data incomplete</p>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-4 md:p-8" data-testid="completed-draft-view">
      <h2 className="text-2xl md:text-3xl font-bold text-white mb-6 md:mb-8">Draft Complete</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-8 w-full max-w-4xl">
        {/* Radiant on left */}
        <TeamPicks team={radiantTeam} picks={radiantPicks} side="radiant" />

        {/* Dire on right */}
        <TeamPicks team={direTeam} picks={direPicks} side="dire" />
      </div>

      {/* View Full Draft button */}
      {onViewFullDraft && (
        <Button
          variant="outline"
          size="lg"
          onClick={onViewFullDraft}
          className="mt-8"
          data-testid="completed-draft-view-full"
        >
          <History className="w-5 h-5 mr-2" />
          View Full Draft
        </Button>
      )}
    </div>
  );
}
