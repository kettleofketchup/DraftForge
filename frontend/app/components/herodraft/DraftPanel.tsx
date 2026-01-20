// frontend/app/components/herodraft/DraftPanel.tsx
import { useMemo } from 'react';
import { heroes } from 'dotaconstants';
import { cn } from '~/lib/utils';
import type { HeroDraft, HeroDraftRound } from '~/components/herodraft/types';

interface DraftPanelProps {
  draft: HeroDraft;
  currentRound: number | null;
}

// Create a lookup map once at module load (not per render)
const heroByIdMap = new Map<number, { img: string; name: string }>();
Object.values(heroes).forEach((hero: any) => {
  heroByIdMap.set(hero.id, {
    img: `https://cdn.cloudflare.steamstatic.com${hero.img}`,
    name: hero.localized_name,
  });
});

function getHeroImage(heroId: number | null): string | null {
  if (!heroId) return null;
  return heroByIdMap.get(heroId)?.img ?? null;
}

function getHeroName(heroId: number | null): string {
  if (!heroId) return '';
  return heroByIdMap.get(heroId)?.name ?? '';
}

export function DraftPanel({ draft, currentRound }: DraftPanelProps) {
  // Memoize team lookups to prevent recalculation on every render
  const { radiantTeam, direTeam } = useMemo(() => {
    const radiant = draft.draft_teams.find((t) => t.is_radiant);
    const dire = draft.draft_teams.find((t) => !t.is_radiant);
    return { radiantTeam: radiant, direTeam: dire };
  }, [draft.draft_teams]);

  const roundsByTeam = useMemo(() => {
    const radiantRounds: HeroDraftRound[] = [];
    const direRounds: HeroDraftRound[] = [];

    draft.rounds.forEach((round) => {
      const team = draft.draft_teams.find((t) => t.id === round.draft_team);
      if (team?.is_radiant) {
        radiantRounds.push(round);
      } else {
        direRounds.push(round);
      }
    });

    return { radiant: radiantRounds, dire: direRounds };
  }, [draft]);

  return (
    <div className="h-full flex flex-col bg-black/80 rounded-lg overflow-hidden" data-testid="herodraft-panel">
      {/* Headers */}
      <div className="flex" data-testid="herodraft-panel-headers">
        <div className="flex-1 p-3 text-center" data-testid="herodraft-panel-radiant-header">
          <h3 className="text-lg font-bold text-green-400 drop-shadow-[0_0_10px_rgba(34,197,94,0.5)]">
            RADIANT
          </h3>
          <p className="text-sm text-muted-foreground" data-testid="herodraft-panel-radiant-captain">
            {radiantTeam?.captain?.nickname || radiantTeam?.captain?.username}
          </p>
        </div>
        <div className="flex-1 p-3 text-center" data-testid="herodraft-panel-dire-header">
          <h3 className="text-lg font-bold text-red-400 drop-shadow-[0_0_10px_rgba(239,68,68,0.5)]">
            DIRE
          </h3>
          <p className="text-sm text-muted-foreground" data-testid="herodraft-panel-dire-captain">
            {direTeam?.captain?.nickname || direTeam?.captain?.username}
          </p>
        </div>
      </div>

      {/* Draft slots */}
      <div className="flex-1 overflow-y-auto p-2" data-testid="herodraft-panel-slots">
        {draft.rounds.map((round) => {
          const isRadiant = draft.draft_teams.find(
            (t) => t.id === round.draft_team
          )?.is_radiant;
          const heroImg = getHeroImage(round.hero_id);
          const heroName = getHeroName(round.hero_id);
          const isActive = round.round_number === currentRound;
          const isPick = round.action_type === 'pick';

          return (
            <div
              key={round.id}
              className={cn(
                'flex items-center gap-2 py-1',
                isActive && 'bg-yellow-500/20 rounded'
              )}
              data-testid={`herodraft-round-${round.round_number}`}
              data-round-active={isActive}
              data-round-state={round.state}
            >
              {/* Radiant slot */}
              <div
                className={cn(
                  'flex-1 flex justify-end',
                  !isRadiant && 'invisible'
                )}
                data-testid={`herodraft-round-${round.round_number}-radiant-slot`}
              >
                {isRadiant && (
                  <div
                    className={cn(
                      'rounded border-2 overflow-hidden transition-all',
                      isPick ? 'w-16 h-10' : 'w-12 h-8',
                      round.state === 'completed'
                        ? 'border-green-500/50'
                        : isActive
                        ? 'border-yellow-400 animate-pulse'
                        : 'border-gray-700',
                      round.action_type === 'ban' && round.state === 'completed' && 'grayscale'
                    )}
                    title={heroName}
                    data-testid={`herodraft-round-${round.round_number}-hero`}
                    data-hero-id={round.hero_id}
                  >
                    {heroImg ? (
                      <img
                        src={heroImg}
                        alt={heroName}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full bg-gray-800 flex items-center justify-center text-xs text-muted-foreground">
                        {round.action_type === 'ban' ? 'BAN' : 'PICK'}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Round number */}
              <div
                className={cn(
                  'w-8 text-center text-sm font-mono',
                  isActive ? 'text-yellow-400 font-bold' : 'text-muted-foreground'
                )}
                data-testid={`herodraft-round-${round.round_number}-number`}
              >
                {round.round_number}
              </div>

              {/* Dire slot */}
              <div
                className={cn(
                  'flex-1 flex justify-start',
                  isRadiant && 'invisible'
                )}
                data-testid={`herodraft-round-${round.round_number}-dire-slot`}
              >
                {!isRadiant && (
                  <div
                    className={cn(
                      'rounded border-2 overflow-hidden transition-all',
                      isPick ? 'w-16 h-10' : 'w-12 h-8',
                      round.state === 'completed'
                        ? 'border-red-500/50'
                        : isActive
                        ? 'border-yellow-400 animate-pulse'
                        : 'border-gray-700',
                      round.action_type === 'ban' && round.state === 'completed' && 'grayscale'
                    )}
                    title={heroName}
                    data-testid={`herodraft-round-${round.round_number}-hero`}
                    data-hero-id={round.hero_id}
                  >
                    {heroImg ? (
                      <img
                        src={heroImg}
                        alt={heroName}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full bg-gray-800 flex items-center justify-center text-xs text-muted-foreground">
                        {round.action_type === 'ban' ? 'BAN' : 'PICK'}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
