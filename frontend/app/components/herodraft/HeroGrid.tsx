// frontend/app/components/herodraft/HeroGrid.tsx
import { memo, useCallback, useEffect, useMemo, useRef } from 'react';
import { heroes } from 'dotaconstants';
import { Input } from '~/components/ui/input';
import { useHeroDraftStore } from '~/store/heroDraftStore';
import { cn } from '~/lib/utils';
import { heroMatchesSearch } from '~/lib/dota/heroes';
import { FastTooltip } from '~/components/ui/tooltip';

// Memoized hero button to prevent re-renders
// IMPORTANT: Don't pass searchQuery directly - pass pre-computed booleans instead
// to avoid all 508 buttons re-rendering on every keystroke
interface HeroButtonProps {
  hero: { id: number; name: string; icon: string };
  available: boolean;
  isHighlighted: boolean; // matches && hasSearchQuery && available
  isDimmed: boolean; // !available || (!matches && hasSearchQuery)
  isSelected: boolean;
  disabled: boolean;
  onClick: (heroId: number) => void;
}

const HeroButton = memo(function HeroButton({
  hero,
  available,
  isHighlighted,
  isDimmed,
  isSelected,
  disabled,
  onClick,
}: HeroButtonProps) {
  return (
    <FastTooltip content={hero.name} className="text-xs">
      <button
        type="button"
        style={{ padding: 0, margin: 0, lineHeight: 0 }}
        onClick={() => {
          if (!disabled && available) {
            onClick(hero.id);
          }
        }}
        // Don't use HTML disabled - it prevents hover states for spectators
        className={cn(
          'size-[20px] sm:size-[24px] md:size-[28px] lg:size-[36px] xl:size-[48px] 2xl:size-[56px] p-0.5',
          'rounded-full bg-gradient-to-b from-slate-600 to-slate-800',
          'border border-slate-500/50 shadow-md shadow-black/50',
          'hover:from-slate-500 hover:to-slate-700 hover:scale-110 hover:z-10 hover:shadow-lg hover:shadow-black/60',
          'transition-all duration-150',
          isSelected && 'ring-2 ring-yellow-400 scale-110 z-10 from-yellow-600/50 to-slate-800',
          isHighlighted && 'ring-2 ring-green-400 from-green-600/30 to-slate-800',
          isDimmed && 'opacity-30 grayscale',
          !available && 'cursor-not-allowed'
        )}
        data-testid={`herodraft-hero-${hero.id}`}
        data-hero-id={hero.id}
        data-hero-name={hero.name}
        data-hero-available={available}
        data-hero-selected={isSelected}
      >
        <img
          src={hero.icon}
          alt={hero.name}
          style={{ display: 'block' }}
          className="size-full rounded-full object-cover"
        />
      </button>
    </FastTooltip>
  );
});

interface HeroGridProps {
  onHeroClick: (heroId: number) => void;
  disabled: boolean;
  showActionButton: boolean;
  /** Current action type (ban or pick) for visual feedback */
  currentAction?: 'ban' | 'pick';
  /** Whether it's the current user's turn */
  isMyTurn?: boolean;
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

export function HeroGrid({ onHeroClick, disabled, showActionButton, currentAction, isMyTurn }: HeroGridProps) {
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Use selectors to prevent re-renders when unrelated state changes
  const searchQuery = useHeroDraftStore((state) => state.searchQuery);
  const setSearchQuery = useHeroDraftStore((state) => state.setSearchQuery);
  const selectedHeroId = useHeroDraftStore((state) => state.selectedHeroId);
  const setSelectedHeroId = useHeroDraftStore((state) => state.setSelectedHeroId);
  // Select draft rounds directly for memoization
  const draftRounds = useHeroDraftStore((state) => state.draft?.rounds);

  // Auto-focus search when typing anywhere (unless in a dialog/input)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Skip if already focused on an input or textarea
      const activeEl = document.activeElement;
      if (
        activeEl instanceof HTMLInputElement ||
        activeEl instanceof HTMLTextAreaElement
      ) {
        return;
      }

      // Only handle printable characters (single character, no ctrl/alt/meta)
      if (e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
        // Focus the input and let the keypress naturally type into it
        searchInputRef.current?.focus();
        // Don't prevent default - let the key go through to the now-focused input
      }

      // Handle Escape to clear search
      if (e.key === 'Escape') {
        e.preventDefault();
        setSearchQuery('');
        searchInputRef.current?.blur();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [setSearchQuery]);

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

  const isHeroAvailable = useCallback(
    (heroId: number) => !usedHeroIds.includes(heroId),
    [usedHeroIds]
  );

  const matchesSearch = useCallback(
    (heroId: number) => filteredHeroes.some((h) => h.id === heroId),
    [filteredHeroes]
  );

  const handleHeroClick = useCallback(
    (heroId: number) => {
      setSelectedHeroId(heroId);
      onHeroClick(heroId);
    },
    [setSelectedHeroId, onHeroClick]
  );

  // Determine overlay color based on current action when it's user's turn
  const actionOverlay = isMyTurn && currentAction
    ? currentAction === 'ban'
      ? 'bg-red-900/40'  // Dark red tint for bans
      : 'bg-green-900/40'  // Dark green tint for picks
    : '';

  return (
    <div className={cn("flex flex-col h-full overflow-hidden relative", actionOverlay)} data-testid="herodraft-hero-grid">
      <div className="p-2 shrink-0" data-testid="herodraft-search-container">
        <Input
          ref={searchInputRef}
          type="text"
          placeholder="Search heroes..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full"
          data-testid="herodraft-hero-search"
        />
      </div>

      <div className="flex-1 flex flex-col p-1 min-h-0 gap-1" data-testid="herodraft-hero-list">
        {ATTRIBUTE_ORDER.map((attr) => {
          const heroesForAttr = heroList.filter((h) => h.attr === attr);
          return (
            <div
              key={attr}
              className={cn('rounded p-1.5 flex-1 min-h-0', ATTRIBUTE_COLORS[attr])}
              data-testid={`herodraft-attr-section-${attr}`}
            >
              <h3 className="text-[10px] font-semibold mb-1 text-white/70" data-testid={`herodraft-attr-label-${attr}`}>
                {ATTRIBUTE_LABELS[attr]}
              </h3>
              <div
                className="flex flex-wrap content-start gap-2"
                data-testid={`herodraft-attr-grid-${attr}`}
              >
                {heroesForAttr.map((hero) => {
                  const available = isHeroAvailable(hero.id);
                  const matches = matchesSearch(hero.id);
                  const hasSearchQuery = !!searchQuery;
                  return (
                    <HeroButton
                      key={hero.id}
                      hero={hero}
                      available={available}
                      isHighlighted={matches && hasSearchQuery && available}
                      isDimmed={!available || (!matches && hasSearchQuery)}
                      isSelected={selectedHeroId === hero.id}
                      disabled={disabled}
                      onClick={handleHeroClick}
                    />
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
