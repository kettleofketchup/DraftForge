import { heroes } from 'dotaconstants';
import { memo, useCallback, useEffect, useMemo, useRef } from 'react';
import { brandBg } from '~/components/ui/buttons/styles';
import { Input } from '~/components/ui/input';
import { ScrollArea } from '~/components/ui/scroll-area';
import { FastTooltip } from '~/components/ui/tooltip';
import { DisplayName } from '~/components/user/avatar';
import { heroMatchesSearch } from '~/lib/dota/heroes';
import { cn } from '~/lib/utils';
import { useHeroDraftStore } from '~/store/heroDraftStore';
import { useUserStore } from '~/store/userStore';
import { HeroSuggestMenu } from './chat/HeroSuggestMenu';
import {
  activeSuggestions,
  type HeroSuggestions,
  NO_SUGGESTIONS,
} from './chat/suggestions';
import { isOverlaidByOtherLayer } from './keyboardLayers';
import { SuggesterStack } from './SuggesterStack';

// Takes precomputed booleans, not searchQuery, so a keystroke doesn't re-render every button.
interface HeroButtonProps {
  hero: { id: number; name: string; icon: string };
  available: boolean;
  isHighlighted: boolean;
  isDimmed: boolean;
  isSelected: boolean;
  disabled: boolean;
  onClick: (heroId: number) => void;
  suggestions: HeroSuggestions;
  showBanSuggestions: boolean;
  emphasis: 'pick' | 'ban' | null;
}

function suggestionLabel(name: string, s: HeroSuggestions, bans: boolean) {
  const parts = [name];
  const names = (users: HeroSuggestions['pick']) =>
    users.map((u) => DisplayName(u)).join(', ');
  if (s.pick.length) parts.push(`Pick: ${names(s.pick)}`);
  if (bans && s.ban.length) parts.push(`Ban: ${names(s.ban)}`);
  return parts.join(' · ');
}

const HeroButton = memo(function HeroButton({
  hero,
  available,
  isHighlighted,
  isDimmed,
  isSelected,
  disabled,
  onClick,
  suggestions,
  showBanSuggestions,
  emphasis,
}: HeroButtonProps) {
  const pick = available ? suggestions.pick : NO_SUGGESTIONS.pick;
  const ban =
    available && showBanSuggestions ? suggestions.ban : NO_SUGGESTIONS.ban;
  return (
    <FastTooltip
      content={suggestionLabel(hero.name, { pick, ban }, showBanSuggestions)}
      className="text-xs"
    >
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
          'relative size-[24px] sm:size-[28px] md:size-[32px] lg:size-[40px] xl:size-[48px] 2xl:size-[56px] shrink-0 p-0.5',
          'rounded-full bg-gradient-to-b from-base-100 to-base-400',
          'border border-border shadow-md shadow-black/50',
          'hover:from-base-50 hover:to-base-200 hover:scale-110 hover:z-10 hover:shadow-lg hover:shadow-black/60',
          'transition-all duration-150',
          isSelected &&
            'ring-2 ring-turn scale-110 z-10 from-turn/40 to-base-400',
          available &&
            emphasis === 'pick' &&
            'z-10 scale-105 ring-2 ring-pick brightness-125 shadow-lg shadow-pick/60 from-pick/50 to-base-400',
          available &&
            emphasis === 'ban' &&
            'z-10 scale-105 ring-2 ring-ban brightness-125 shadow-lg shadow-ban/60 from-ban/50 to-base-400',
          isHighlighted &&
            'ring-2 ring-search-match from-search-match/30 to-base-400',
          isDimmed && 'opacity-30 grayscale',
          !available && 'cursor-not-allowed',
        )}
        data-testid={`herodraft-hero-${hero.id}`}
        data-hero-id={hero.id}
        data-hero-name={hero.name}
        data-hero-available={available}
        data-hero-selected={isSelected}
        data-hero-disabled={disabled}
        data-hero-emphasis={available && emphasis ? emphasis : undefined}
      >
        <SuggesterStack users={pick} kind="pick" heroId={hero.id} />
        <SuggesterStack users={ban} kind="ban" heroId={hero.id} />
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
  currentAction?: 'ban' | 'pick';
  isMyTurn?: boolean;
  canSuggest?: boolean;
}

const KEYDOWN_IGNORE_SELECTOR = '[data-herodraft-chat], [role="menu"]';

type HeroAttribute = 'str' | 'agi' | 'int' | 'all';

const ATTRIBUTE_ORDER: HeroAttribute[] = ['str', 'agi', 'int', 'all'];
const ATTRIBUTE_LABELS: Record<HeroAttribute, string> = {
  str: 'Strength',
  agi: 'Agility',
  int: 'Intelligence',
  all: 'Universal',
};

const ATTRIBUTE_COLORS: Record<HeroAttribute, string> = {
  str: 'bg-attr-str/20',
  agi: 'bg-attr-agi/20',
  int: 'bg-attr-int/20',
  all: 'bg-attr-all/20',
};

export function HeroGrid({
  onHeroClick,
  disabled,
  showActionButton,
  currentAction,
  isMyTurn,
  canSuggest = false,
}: HeroGridProps) {
  const searchInputRef = useRef<HTMLInputElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);

  const searchQuery = useHeroDraftStore((state) => state.searchQuery);
  const setSearchQuery = useHeroDraftStore((state) => state.setSearchQuery);
  const selectedHeroId = useHeroDraftStore((state) => state.selectedHeroId);
  const setSelectedHeroId = useHeroDraftStore(
    (state) => state.setSelectedHeroId,
  );
  const draftRounds = useHeroDraftStore((state) => state.draft?.rounds);
  const suggestHero = useHeroDraftStore((state) => state.suggestHero);
  const unsuggestHero = useHeroDraftStore((state) => state.unsuggestHero);
  const chatMessages = useHeroDraftStore((state) => state.chat.messages);
  const selfId = useUserStore((state) => state.currentUser?.pk);
  const suggestions = useMemo(
    () => activeSuggestions(chatMessages),
    [chatMessages],
  );
  const showBanSuggestions = currentAction === 'ban';
  const ownSuggestions = useCallback(
    (heroId: number) => {
      const s = suggestions.get(heroId) ?? NO_SUGGESTIONS;
      return {
        pick: s.pick.some((u) => u.pk === selfId),
        ban: s.ban.some((u) => u.pk === selfId),
      };
    },
    [suggestions, selfId],
  );
  const chatInset = useHeroDraftStore((state) => state.chatPanelInset);

  // Typing anywhere outside an input or menu focuses the search box.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const activeEl = document.activeElement;
      if (
        activeEl instanceof HTMLInputElement ||
        activeEl instanceof HTMLTextAreaElement
      ) {
        return;
      }
      if (
        (e.target instanceof Element &&
          e.target.closest(KEYDOWN_IGNORE_SELECTOR)) ||
        isOverlaidByOtherLayer(gridRef.current)
      ) {
        return;
      }

      if (e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
        searchInputRef.current?.focus();
        // No preventDefault: the key lands in the now-focused input.
      }

      if (e.key === 'Escape') {
        e.preventDefault();
        setSearchQuery('');
        searchInputRef.current?.blur();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [setSearchQuery]);

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
    // Also matches aliases: short names, nicknames, DotA 1 names.
    return heroList.filter((hero) => heroMatchesSearch(hero.id, searchQuery));
  }, [heroList, searchQuery]);

  const isHeroAvailable = useCallback(
    (heroId: number) => !usedHeroIds.includes(heroId),
    [usedHeroIds],
  );

  const matchesSearch = useCallback(
    (heroId: number) => filteredHeroes.some((h) => h.id === heroId),
    [filteredHeroes],
  );

  const handleHeroClick = useCallback(
    (heroId: number) => {
      setSelectedHeroId(heroId);
      onHeroClick(heroId);
    },
    [setSelectedHeroId, onHeroClick],
  );

  const actionOverlay =
    isMyTurn && currentAction
      ? currentAction === 'ban'
        ? 'bg-ban-surface/80'
        : 'bg-pick-surface/80'
      : '';

  const heroListEl = (
    <div
      className={cn(
        'flex-1 flex flex-col p-1 min-h-0 gap-1',
        chatInset > 0 && 'overflow-y-auto',
      )}
      // Lets rows under the open chat panel scroll up above it.
      style={
        chatInset > 0
          ? { paddingBottom: chatInset, scrollPaddingBottom: chatInset }
          : undefined
      }
      data-testid="herodraft-hero-list"
    >
      {ATTRIBUTE_ORDER.map((attr) => {
        const heroesForAttr = heroList.filter((h) => h.attr === attr);
        return (
          <ScrollArea
            key={attr}
            className={cn(
              'rounded p-1.5 flex-1',
              chatInset > 0 ? 'min-h-fit' : 'min-h-0',
              ATTRIBUTE_COLORS[attr],
            )}
            data-testid={`herodraft-attr-section-${attr}`}
          >
            <h3
              className="text-[10px] font-semibold mb-1 text-white/70"
              data-testid={`herodraft-attr-label-${attr}`}
            >
              {ATTRIBUTE_LABELS[attr]}
            </h3>
            <div
              // p-2 fits a full suggester stack overhanging an edge hero at every breakpoint.
              className="flex flex-wrap content-start gap-2 p-2"
              data-testid={`herodraft-attr-grid-${attr}`}
            >
              {heroesForAttr.map((hero) => {
                const available = isHeroAvailable(hero.id);
                const matches = matchesSearch(hero.id);
                const hasSearchQuery = !!searchQuery;
                const heroSuggestions =
                  suggestions.get(hero.id) ?? NO_SUGGESTIONS;
                const emphasis =
                  isMyTurn && currentAction
                    ? heroSuggestions[currentAction].length > 0
                      ? currentAction
                      : null
                    : null;
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
                    suggestions={heroSuggestions}
                    showBanSuggestions={showBanSuggestions}
                    emphasis={emphasis}
                  />
                );
              })}
            </div>
          </ScrollArea>
        );
      })}
    </div>
  );

  return (
    <div
      ref={gridRef}
      className={cn(
        'flex flex-col h-full overflow-hidden relative',
        brandBg,
        actionOverlay,
      )}
      data-testid="herodraft-hero-grid"
    >
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

      <HeroSuggestMenu
        enabled={canSuggest}
        onSuggest={suggestHero}
        onUnsuggest={unsuggestHero}
        ownSuggestions={ownSuggestions}
      >
        {heroListEl}
      </HeroSuggestMenu>
    </div>
  );
}
