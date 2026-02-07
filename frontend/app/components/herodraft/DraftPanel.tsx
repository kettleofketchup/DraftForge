// frontend/app/components/herodraft/DraftPanel.tsx
import { useMemo, useRef, useEffect } from 'react';
import { heroes } from 'dotaconstants';
import { cn } from '~/lib/utils';
import { brandBg } from '~/components/ui/buttons/styles';
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

  // Order teams: first pick on left, second pick on right
  // Falls back to array order when is_first_pick is null (pre-coin-flip)
  const { leftTeam, rightTeam } = useMemo(() => {
    const first = draft.draft_teams.find((t) => t.is_first_pick === true);
    const second = draft.draft_teams.find((t) => t.is_first_pick === false);
    if (first && second) return { leftTeam: first, rightTeam: second };
    const radiant = draft.draft_teams.find((t) => t.is_radiant);
    const dire = draft.draft_teams.find((t) => !t.is_radiant);
    return { leftTeam: radiant ?? draft.draft_teams[0], rightTeam: dire ?? draft.draft_teams[1] };
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
    <div className={cn("h-full flex flex-col overflow-hidden", brandBg)} data-testid="herodraft-panel">
      {/* Headers */}
      <div className="flex shrink-0 border-b border-gray-700">
        <div className="flex-1 py-1 px-2 text-center">
          <h3 className={cn("text-xs font-bold", leftTeam?.is_radiant ? "text-green-400" : "text-red-400")}>
            {leftTeam?.is_radiant ? 'RADIANT' : 'DIRE'}
          </h3>
          <p className="text-[9px] text-muted-foreground truncate">
            {leftTeam?.captain ? DisplayName(leftTeam.captain) : ''}
          </p>
        </div>
        <div className="w-6 sm:w-8 md:w-10 lg:w-12 shrink-0" /> {/* Center spacer */}
        <div className="flex-1 py-1 px-2 text-center">
          <h3 className={cn("text-xs font-bold", rightTeam?.is_radiant ? "text-green-400" : "text-red-400")}>
            {rightTeam?.is_radiant ? 'RADIANT' : 'DIRE'}
          </h3>
          <p className="text-[9px] text-muted-foreground truncate">
            {rightTeam?.captain ? DisplayName(rightTeam.captain) : ''}
          </p>
        </div>
      </div>

      {/* Draft timeline */}
      <ScrollArea className="flex-1 min-h-0" type="always">
        <div className="flex flex-col gap-1 py-4">
          {sortedRounds.map((round) => {
            const team = draft.draft_teams.find((t) => t.id === round.draft_team);
            const isLeft = team?.id === leftTeam?.id;
            const heroImg = getHeroImage(round.hero_id);
            const heroName = getHeroName(round.hero_id);
            // Highlight the first non-completed round (active or planned)
            const isActive = round.round_number === activeRoundNumber;
            const isPick = round.action_type === 'pick';
            const isBan = round.action_type === 'ban';
            const isCompleted = round.state === 'completed';

            // Container width matches pick width so bans center-align with picks
            const slotWidth = 'w-12 sm:w-14 md:w-16 lg:w-20 xl:w-24';
            const pickHeight = 'h-7 sm:h-8 md:h-9 lg:h-10 xl:h-12';
            const banSize = 'w-10 h-6 sm:w-12 sm:h-7 md:w-14 md:h-8 lg:w-16 lg:h-9 xl:w-20 xl:h-11';

            // Octagon clip-path adjusted for ~1.7:1 wide aspect ratio (hero slots)
            const octagonClip = '[clip-path:polygon(15%_0%,85%_0%,100%_25%,100%_75%,85%_100%,15%_100%,0%_75%,0%_25%)]';
            // Octagon clip-path for square elements (round number indicators)
            const octagonSquare = '[clip-path:polygon(30%_0%,70%_0%,100%_30%,100%_70%,70%_100%,30%_100%,0%_70%,0%_30%)]';

            // Indicator on outer side: left for Radiant, right for Dire
            const indicator = isCompleted && (
              isBan
                ? <span className="text-xs sm:text-sm leading-none text-red-500 font-bold">✕</span>
                : isPick
                  ? <span className="text-xs sm:text-sm leading-none text-green-500 font-bold">✓</span>
                  : null
            );

            const heroSlot = (
              <div className={cn('flex items-center gap-1.5 px-1', !isLeft && 'flex-row-reverse')}>
                {/* Indicator on outer side (left for Radiant, right for Dire) */}
                {indicator}

                {/* Fixed-width container so bans and picks share the same center */}
                <div className={cn(slotWidth, 'flex items-center justify-center')}>
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
                          'p-[3px] transition-all',
                          isActive ? 'bg-yellow-400' : isCompleted ? 'bg-red-500/70' : 'bg-red-900/60',
                          banSize
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
                            <div className="w-full h-full flex items-center justify-center text-[9px] sm:text-[10px] font-bold bg-red-950/60 text-red-400 [text-shadow:0_0_4px_rgba(0,0,0,0.8)]">
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
                        isCompleted ? 'border-green-500/70' : isBan ? 'border-red-500/40' : 'border-green-500/40',
                        isActive && 'border-yellow-400 border-2',
                        slotWidth, pickHeight
                      )}
                      data-testid={`herodraft-round-${round.round_number}-hero`}
                      data-hero-id={round.hero_id}
                    >
                      {heroImg ? (
                        <img src={heroImg} alt={heroName} className="w-full h-full object-cover" />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-[9px] sm:text-[10px] font-bold bg-green-950/60 text-green-400 [text-shadow:0_0_4px_rgba(0,0,0,0.8)]">
                          PICK
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );

            const wrappedSlot = heroName ? (
              <Tooltip>
                <TooltipTrigger asChild>{heroSlot}</TooltipTrigger>
                <TooltipContent side={isLeft ? 'left' : 'right'} className="text-xs">
                  {heroName}
                </TooltipContent>
              </Tooltip>
            ) : heroSlot;

            return (
              <div
                key={round.id}
                ref={isActive ? activeRoundRef : undefined}
                className="flex items-center"
                data-testid={`herodraft-round-${round.round_number}`}
                data-round-active={isActive}
                data-round-state={round.state}
              >
                {/* Radiant side */}
                <div className="flex-1 flex justify-end items-center pr-0.5">
                  {isLeft && wrappedSlot}
                </div>

                {/* Center number with line */}
                <div className="w-6 sm:w-8 md:w-10 lg:w-12 shrink-0 flex items-center justify-center relative">
                  {/* Line pointing to team */}
                  <div
                    className={cn(
                      'absolute top-1/2 -translate-y-1/2 h-px',
                      isLeft ? 'right-1/2 left-0' : 'left-1/2 right-0',
                      isActive
                        ? 'bg-yellow-400'
                        : isCompleted
                          ? isPick ? 'bg-green-500/50' : 'bg-red-500/50'
                          : 'bg-gray-600'
                    )}
                  />
                  {/* Number indicator — octagon for bans, square for picks */}
                  {/* Outer wrapper provides highlight border via padding + clip-path */}
                  <div
                    className={cn(
                      'relative z-10',
                      isBan ? octagonSquare : 'rounded-[2px]',
                      isActive
                        ? isBan
                          ? 'bg-yellow-400 p-[2px] w-6 h-6 sm:w-7 sm:h-7 md:w-8 md:h-8'
                          : 'bg-yellow-400 p-[2px] w-6 h-6 sm:w-7 sm:h-7 md:w-8 md:h-8'
                        : 'w-5 h-5 sm:w-6 sm:h-6 md:w-7 md:h-7'
                    )}
                  >
                    <div
                      className={cn(
                        'w-full h-full flex items-center justify-center text-[10px] sm:text-xs md:text-sm font-bold leading-none',
                        isBan ? octagonSquare : 'rounded-[2px]',
                        isActive
                          ? isBan ? 'bg-red-900 text-yellow-400' : 'bg-green-900 text-yellow-400'
                          : isBan
                            ? 'bg-red-900 text-red-400'
                            : isCompleted
                              ? 'bg-green-900 text-green-400'
                              : 'bg-green-950 text-green-500'
                      )}
                    >
                      {round.round_number}
                    </div>
                  </div>
                </div>

                {/* Dire side */}
                <div className="flex-1 flex justify-start items-center pl-0.5">
                  {!isLeft && wrappedSlot}
                </div>
              </div>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}
