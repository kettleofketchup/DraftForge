// frontend/app/components/herodraft/DraftPanel.tsx
import { useMemo } from 'react';
import { heroes } from 'dotaconstants';
import { cn } from '~/lib/utils';
import type { HeroDraft, HeroDraftRound } from '~/components/herodraft/types';
import { DisplayName } from '~/components/user/avatar';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';

interface DraftPanelProps {
  draft: HeroDraft;
  currentRound: number | null;
}

// Create a lookup map once at module load
const heroByIdMap = new Map<number, { img: string; icon: string; name: string }>();
Object.values(heroes).forEach((hero: any) => {
  heroByIdMap.set(hero.id, {
    img: `https://cdn.cloudflare.steamstatic.com${hero.img}`,
    icon: `https://cdn.cloudflare.steamstatic.com${hero.icon}`,
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
  // Memoize team lookups
  const { radiantTeam, direTeam } = useMemo(() => {
    const radiant = draft.draft_teams.find((t) => t.is_radiant);
    const dire = draft.draft_teams.find((t) => !t.is_radiant);
    return { radiantTeam: radiant, direTeam: dire };
  }, [draft.draft_teams]);

  // Sort rounds by round_number for proper order
  const sortedRounds = useMemo(() => {
    return [...draft.rounds].sort((a, b) => a.round_number - b.round_number);
  }, [draft.rounds]);

  return (
    <div className="h-full flex flex-col bg-black/90 overflow-hidden" data-testid="herodraft-panel">
      {/* Headers */}
      <div className="flex shrink-0 border-b border-gray-700">
        <div className="flex-1 py-1 px-2 text-center">
          <h3 className="text-xs font-bold text-green-400">RADIANT</h3>
          <p className="text-[9px] text-muted-foreground truncate">
            {radiantTeam?.captain ? DisplayName(radiantTeam.captain) : ''}
          </p>
        </div>
        <div className="w-6 sm:w-8 md:w-10 lg:w-12 shrink-0" /> {/* Center spacer */}
        <div className="flex-1 py-1 px-2 text-center">
          <h3 className="text-xs font-bold text-red-400">DIRE</h3>
          <p className="text-[9px] text-muted-foreground truncate">
            {direTeam?.captain ? DisplayName(direTeam.captain) : ''}
          </p>
        </div>
      </div>

      {/* Draft timeline */}
      <div className="flex-1 overflow-y-auto min-h-0">
        <div className="flex flex-col">
          {sortedRounds.map((round) => {
            const team = draft.draft_teams.find((t) => t.id === round.draft_team);
            const isRadiant = team?.is_radiant;
            const heroImg = getHeroImage(round.hero_id);
            const heroName = getHeroName(round.hero_id);
            const isActive = round.round_number === currentRound;
            const isPick = round.action_type === 'pick';
            const isBan = round.action_type === 'ban';
            const isCompleted = round.state === 'completed';

            // Slot heights - responsive sizes (sm -> md -> lg -> xl)
            // Bans: smaller, Picks: larger
            const slotHeight = isPick
              ? 'h-7 sm:h-8 md:h-9 lg:h-10 xl:h-12'
              : 'h-5 sm:h-6 md:h-7 lg:h-8 xl:h-9';
            const imgSize = isPick
              ? 'w-12 h-7 sm:w-14 sm:h-8 md:w-16 md:h-9 lg:w-20 lg:h-10 xl:w-24 xl:h-12'
              : 'w-9 h-5 sm:w-10 sm:h-6 md:w-12 md:h-7 lg:w-14 lg:h-8 xl:w-16 xl:h-9';

            const heroSlot = (
              <div className="flex items-start gap-0.5">
                {/* Ban indicator - red X outside left, aligned to top */}
                {isBan && isCompleted && (
                  <span className="text-[10px] sm:text-xs leading-none text-red-500 font-bold">✕</span>
                )}
                {/* Hero image */}
                <div
                  className={cn(
                    'overflow-hidden border transition-all relative',
                    isCompleted
                      ? isRadiant ? 'border-green-500/70' : 'border-red-500/70'
                      : 'border-gray-600',
                    isActive && 'border-yellow-400 border-2',
                    imgSize
                  )}
                  data-testid={`herodraft-round-${round.round_number - 1}-hero`}
                  data-hero-id={round.hero_id}
                >
                  {heroImg ? (
                    <>
                      <img src={heroImg} alt={heroName} className="w-full h-full object-cover" />
                      {/* Red tint overlay for bans */}
                      {isBan && isCompleted && (
                        <div className="absolute inset-0 bg-red-600/20" />
                      )}
                    </>
                  ) : (
                    <div className={cn(
                      'w-full h-full flex items-center justify-center text-[7px] font-medium',
                      isRadiant ? 'bg-green-900/40 text-green-500/60' : 'bg-red-900/40 text-red-500/60'
                    )}>
                      {isBan ? 'BAN' : 'PICK'}
                    </div>
                  )}
                </div>
                {/* Pick indicator - green checkmark outside right, aligned to top */}
                {isPick && isCompleted && (
                  <span className="text-[10px] sm:text-xs leading-none text-green-500 font-bold">✓</span>
                )}
              </div>
            );

            const wrappedSlot = heroName ? (
              <Tooltip>
                <TooltipTrigger asChild>{heroSlot}</TooltipTrigger>
                <TooltipContent side={isRadiant ? 'left' : 'right'} className="text-xs">
                  {heroName}
                </TooltipContent>
              </Tooltip>
            ) : heroSlot;

            return (
              <div
                key={round.id}
                className={cn('flex items-center', slotHeight)}
                data-testid={`herodraft-round-${round.round_number - 1}`}
                data-round-active={isActive}
                data-round-state={round.state}
              >
                {/* Radiant side */}
                <div className="flex-1 flex justify-end items-center pr-0.5">
                  {isRadiant && wrappedSlot}
                </div>

                {/* Center number with line */}
                <div className="w-6 sm:w-8 md:w-10 lg:w-12 shrink-0 flex items-center justify-center relative">
                  {/* Line pointing to team */}
                  <div
                    className={cn(
                      'absolute top-1/2 -translate-y-1/2 h-px',
                      isRadiant ? 'right-1/2 left-0' : 'left-1/2 right-0',
                      isActive
                        ? 'bg-yellow-400'
                        : isCompleted
                          ? isRadiant ? 'bg-green-500/50' : 'bg-red-500/50'
                          : 'bg-gray-600'
                    )}
                  />
                  {/* Number circle */}
                  <div
                    className={cn(
                      'relative z-10 w-4 h-4 sm:w-5 sm:h-5 md:w-6 md:h-6 rounded-full flex items-center justify-center text-[8px] sm:text-[10px] md:text-xs font-bold',
                      isActive
                        ? 'bg-yellow-400 text-black'
                        : isCompleted
                          ? 'bg-gray-700 text-gray-400'
                          : 'bg-gray-800 text-gray-500 border border-gray-600'
                    )}
                  >
                    {round.round_number - 1}
                  </div>
                </div>

                {/* Dire side */}
                <div className="flex-1 flex justify-start items-center pl-0.5">
                  {!isRadiant && wrappedSlot}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
