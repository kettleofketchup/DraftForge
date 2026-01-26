// frontend/app/components/herodraft/HeroGrid.tsx
import { useMemo } from 'react';
import { heroes } from 'dotaconstants';
import { Input } from '~/components/ui/input';
import { useHeroDraftStore } from '~/store/heroDraftStore';
import { cn } from '~/lib/utils';
import { heroMatchesSearch } from '~/lib/dota/heroes';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';

interface HeroGridProps {
  onHeroClick: (heroId: number) => void;
  disabled: boolean;
  showActionButton: boolean;
}

type HeroAttribute = 'str' | 'agi' | 'int' | 'all';

const ATTRIBUTE_ORDER: HeroAttribute[] = ['str', 'agi', 'int', 'all'];
const ATTRIBUTE_LABELS: Record<HeroAttribute, string> = {
  str: 'Strength',
  agi: 'Agility',
  int: 'Intelligence',
  all: 'Universal',
};

const ATTRIBUTE_COLORS: Record<HeroAttribute, string> = {
  str: 'bg-red-900/40',
  agi: 'bg-green-900/40',
  int: 'bg-blue-900/40',
  all: 'bg-yellow-900/40',
};

export function HeroGrid({ onHeroClick, disabled, showActionButton }: HeroGridProps) {
  // Use selectors to prevent re-renders when unrelated state changes
  const searchQuery = useHeroDraftStore((state) => state.searchQuery);
  const setSearchQuery = useHeroDraftStore((state) => state.setSearchQuery);
  const selectedHeroId = useHeroDraftStore((state) => state.selectedHeroId);
  const setSelectedHeroId = useHeroDraftStore((state) => state.setSelectedHeroId);
  // Select draft rounds directly for memoization
  const draftRounds = useHeroDraftStore((state) => state.draft?.rounds);

  // Memoize used hero IDs to prevent recalculation unless rounds change
  const usedHeroIds = useMemo(() => {
    if (!draftRounds) return [];
    return draftRounds
      .filter((r) => r.hero_id !== null)
      .map((r) => r.hero_id as number);
  }, [draftRounds]);

  const heroList = useMemo(() => {
    return Object.values(heroes).map((hero: any) => ({
      id: hero.id,
      name: hero.localized_name,
      attr: hero.primary_attr as HeroAttribute,
      img: `https://cdn.cloudflare.steamstatic.com${hero.img}`,
      icon: `https://cdn.cloudflare.steamstatic.com${hero.icon}`,
    }));
  }, []);

  const filteredHeroes = useMemo(() => {
    // Use heroMatchesSearch to match against all aliases (short names, nicknames, DotA 1 names)
    return heroList.filter((hero) => heroMatchesSearch(hero.id, searchQuery));
  }, [heroList, searchQuery]);

  const isHeroAvailable = (heroId: number) => !usedHeroIds.includes(heroId);
  const matchesSearch = (heroId: number) =>
    filteredHeroes.some((h) => h.id === heroId);

  return (
    <div className="flex flex-col h-full overflow-hidden" data-testid="herodraft-hero-grid">
      <div className="p-2 shrink-0" data-testid="herodraft-search-container">
        <Input
          type="text"
          placeholder="Search heroes..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full"
          data-testid="herodraft-hero-search"
        />
      </div>

      <div className="flex-1 overflow-y-auto p-1 min-h-0 space-y-2" data-testid="herodraft-hero-list">
        {ATTRIBUTE_ORDER.map((attr) => {
          const heroesForAttr = heroList.filter((h) => h.attr === attr);
          return (
            <div
              key={attr}
              className={cn('rounded p-1.5', ATTRIBUTE_COLORS[attr])}
              data-testid={`herodraft-attr-section-${attr}`}
            >
              <h3 className="text-[10px] font-semibold mb-1 text-white/70" data-testid={`herodraft-attr-label-${attr}`}>
                {ATTRIBUTE_LABELS[attr]}
              </h3>
              <div
                className="flex flex-wrap content-start gap-0.5"
                data-testid={`herodraft-attr-grid-${attr}`}
              >
                {heroesForAttr.map((hero) => {
                  const available = isHeroAvailable(hero.id);
                  const matches = matchesSearch(hero.id);
                  const isSelected = selectedHeroId === hero.id;

                  return (
                    <Tooltip key={hero.id}>
                      <TooltipTrigger asChild>
                        <button
                          type="button"
                          style={{ padding: 0, margin: 0, lineHeight: 0 }}
                          onClick={() => {
                            console.log(`[HeroGrid] Hero clicked:`, {
                              heroId: hero.id,
                              heroName: hero.name,
                              disabled,
                              available,
                              willHandle: !disabled && available,
                            });
                            if (!disabled && available) {
                              setSelectedHeroId(hero.id);
                              onHeroClick(hero.id);
                            }
                          }}
                          disabled={disabled || !available}
                          className={cn(
                            'size-4 sm:size-5 md:size-6 lg:size-7 xl:size-8 rounded-sm border-0 bg-transparent',
                            'hover:ring-1 hover:ring-white/50 hover:scale-110 hover:z-10 transition-transform',
                            isSelected && 'ring-2 ring-yellow-400 scale-110 z-10',
                            (!available || (!matches && searchQuery)) && 'opacity-30 grayscale',
                            disabled && 'cursor-not-allowed'
                          )}
                          data-testid={`herodraft-hero-${hero.id}`}
                          data-hero-name={hero.name}
                          data-hero-available={available}
                          data-hero-selected={isSelected}
                        >
                          <img
                            src={hero.icon}
                            alt={hero.name}
                            style={{ display: 'block' }}
                            className="size-full rounded-sm object-cover"
                          />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="text-xs">
                        {hero.name}
                      </TooltipContent>
                    </Tooltip>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
