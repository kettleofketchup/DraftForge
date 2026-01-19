// frontend/app/components/herodraft/DraftPanel.tsx
import { useMemo } from 'react';
import { heroes } from 'dotaconstants';
import { cn } from '~/lib/utils';
import type { HeroDraft, HeroDraftRound } from '~/components/herodraft/types';

interface DraftPanelProps {
  draft: HeroDraft;
  currentRound: number | null;
}

function getHeroImage(heroId: number | null): string | null {
  if (!heroId) return null;
  const hero = Object.values(heroes).find((h: any) => h.id === heroId);
  return hero ? `https://cdn.cloudflare.steamstatic.com${(hero as any).img}` : null;
}

function getHeroName(heroId: number | null): string {
  if (!heroId) return '';
  const hero = Object.values(heroes).find((h: any) => h.id === heroId);
  return hero ? (hero as any).localized_name : '';
}

export function DraftPanel({ draft, currentRound }: DraftPanelProps) {
  const radiantTeam = draft.draft_teams.find((t) => t.is_radiant);
  const direTeam = draft.draft_teams.find((t) => !t.is_radiant);

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
    <div className="h-full flex flex-col bg-black/80 rounded-lg overflow-hidden">
      {/* Headers */}
      <div className="flex">
        <div className="flex-1 p-3 text-center">
          <h3 className="text-lg font-bold text-green-400 drop-shadow-[0_0_10px_rgba(34,197,94,0.5)]">
            RADIANT
          </h3>
          <p className="text-sm text-muted-foreground">
            {radiantTeam?.captain?.nickname || radiantTeam?.captain?.username}
          </p>
        </div>
        <div className="flex-1 p-3 text-center">
          <h3 className="text-lg font-bold text-red-400 drop-shadow-[0_0_10px_rgba(239,68,68,0.5)]">
            DIRE
          </h3>
          <p className="text-sm text-muted-foreground">
            {direTeam?.captain?.nickname || direTeam?.captain?.username}
          </p>
        </div>
      </div>

      {/* Draft slots */}
      <div className="flex-1 overflow-y-auto p-2">
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
            >
              {/* Radiant slot */}
              <div
                className={cn(
                  'flex-1 flex justify-end',
                  !isRadiant && 'invisible'
                )}
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
              >
                {round.round_number}
              </div>

              {/* Dire slot */}
              <div
                className={cn(
                  'flex-1 flex justify-start',
                  isRadiant && 'invisible'
                )}
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
