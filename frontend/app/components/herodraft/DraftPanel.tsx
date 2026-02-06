// frontend/app/components/herodraft/DraftPanel.tsx
import { useMemo, useRef, useEffect } from 'react';
import { heroes } from 'dotaconstants';
import { cn } from '~/lib/utils';
import type { HeroDraft, HeroDraftRound } from '~/components/herodraft/types';
import { DisplayName } from '~/components/user/avatar';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { ScrollArea } from '~/components/ui/scroll-area';

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
  const activeRoundRef = useRef<HTMLDivElement>(null);

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

  // Find the active round (first round that is 'active' or 'planned', not 'completed')
  // This ensures we highlight the NEXT pick, not a completed one
  const activeRoundNumber = useMemo(() => {
    const activeRound = sortedRounds.find(
      (r) => r.state === 'active' || r.state === 'planned'
    );
    return activeRound?.round_number ?? null;
  }, [sortedRounds]);

  // Autoscroll to active round when it changes
  useEffect(() => {
    if (activeRoundNumber !== null && activeRoundRef.current) {
      activeRoundRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }
  }, [activeRoundNumber]);

  return (
    <div className="h-full flex flex-col bg-black/90 overflow-hidden" data-testid="herodraft-panel">
      {/* Headers */}
      <div className="flex shrink-0 border-b border-gray-700">
        <div className="flex-1 py-1 px-2 text-center">
          <h3 className="text-xs font-bold text-gray-300">RADIANT</h3>
          <p className="text-[9px] text-muted-foreground truncate">
            {radiantTeam?.captain ? DisplayName(radiantTeam.captain) : ''}
          </p>
        </div>
        <div className="w-6 sm:w-8 md:w-10 lg:w-12 shrink-0" /> {/* Center spacer */}
        <div className="flex-1 py-1 px-2 text-center">
          <h3 className="text-xs font-bold text-gray-300">DIRE</h3>
          <p className="text-[9px] text-muted-foreground truncate">
            {direTeam?.captain ? DisplayName(direTeam.captain) : ''}
          </p>
        </div>
      </div>

      {/* Draft timeline */}
      <ScrollArea className="flex-1 min-h-0" type="always">
        <div className="flex flex-col py-4">
          {sortedRounds.map((round) => {
            const team = draft.draft_teams.find((t) => t.id === round.draft_team);
            const isRadiant = team?.is_radiant;
            const heroImg = getHeroImage(round.hero_id);
            const heroName = getHeroName(round.hero_id);
            // Highlight the first non-completed round (active or planned)
            const isActive = round.round_number === activeRoundNumber;
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

            // Octagon clip-path for ban slots (stop-sign shape)
            const octagonClip = '[clip-path:polygon(25%_0%,75%_0%,100%_30%,100%_70%,75%_100%,25%_100%,0%_70%,0%_30%)]';

            const heroSlot = (
              <div className="flex items-start gap-0.5">
                {/* Ban indicator - red X outside left, aligned to top */}
                {isBan && isCompleted && (
                  <span className="text-xs sm:text-sm leading-none text-red-500 font-bold">✕</span>
                )}

                {isBan ? (
                  // Octagon ban slot with red glow
                  <div className={cn(
                    'transition-all',
                    isActive
                      ? 'drop-shadow-[0_0_6px_rgba(250,204,21,0.8)]'
                      : isCompleted
                        ? 'drop-shadow-[0_0_6px_rgba(239,68,68,0.6)]'
                        : 'drop-shadow-[0_0_4px_rgba(239,68,68,0.3)]'
                  )}>
                    <div
                      className={cn(
                        octagonClip,
                        'p-[2px] transition-all',
                        isActive ? 'bg-yellow-400' : isCompleted ? 'bg-red-500/70' : 'bg-red-900/60',
                        imgSize
                      )}
                      data-testid={`herodraft-round-${round.round_number}-hero`}
                      data-hero-id={round.hero_id}
                    >
                      <div className={cn(octagonClip, 'w-full h-full overflow-hidden relative')}>
                        {heroImg ? (
                          <>
                            <img src={heroImg} alt={heroName} className="w-full h-full object-cover" />
                            {isCompleted && (
                              <div className="absolute inset-0 bg-red-600/20" />
                            )}
                          </>
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-[9px] sm:text-[10px] font-medium bg-red-900/40 text-red-500/60">
                            BAN
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ) : (
                  // Rectangular pick slot
                  <div
                    className={cn(
                      'overflow-hidden border transition-all relative',
                      isCompleted ? 'border-green-500/70' : 'border-gray-600',
                      isActive && 'border-yellow-400 border-2',
                      imgSize
                    )}
                    data-testid={`herodraft-round-${round.round_number}-hero`}
                    data-hero-id={round.hero_id}
                  >
                    {heroImg ? (
                      <img src={heroImg} alt={heroName} className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-[9px] sm:text-[10px] font-medium bg-green-900/40 text-green-500/60">
                        PICK
                      </div>
                    )}
                  </div>
                )}

                {/* Pick indicator - green checkmark outside right, aligned to top */}
                {isPick && isCompleted && (
                  <span className="text-xs sm:text-sm leading-none text-green-500 font-bold">✓</span>
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
                ref={isActive ? activeRoundRef : undefined}
                className={cn('flex items-center', slotHeight)}
                data-testid={`herodraft-round-${round.round_number}`}
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
                          ? isPick ? 'bg-green-500/50' : 'bg-red-500/50'
                          : 'bg-gray-600'
                    )}
                  />
                  {/* Number circle */}
                  <div
                    className={cn(
                      'relative z-10 w-5 h-5 sm:w-6 sm:h-6 md:w-7 md:h-7 rounded-full flex items-center justify-center text-[10px] sm:text-xs md:text-sm font-bold',
                      isActive
                        ? 'bg-yellow-400 text-black'
                        : isCompleted
                          ? 'bg-gray-700 text-gray-400'
                          : 'bg-gray-800 text-gray-500 border border-gray-600'
                    )}
                  >
                    {round.round_number}
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
      </ScrollArea>
    </div>
  );
}
