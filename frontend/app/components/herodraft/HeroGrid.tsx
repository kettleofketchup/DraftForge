// frontend/app/components/herodraft/HeroGrid.tsx
import { useMemo } from 'react';
import { heroes } from 'dotaconstants';
import { Input } from '~/components/ui/input';
import { useHeroDraftStore } from '~/store/heroDraftStore';
import { cn } from '~/lib/utils';

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

export function HeroGrid({ onHeroClick, disabled, showActionButton }: HeroGridProps) {
  const { searchQuery, setSearchQuery, getUsedHeroIds, selectedHeroId, setSelectedHeroId } =
    useHeroDraftStore();

  const usedHeroIds = getUsedHeroIds();

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
    const query = searchQuery.toLowerCase();
    return heroList.filter((hero) => hero.name.toLowerCase().includes(query));
  }, [heroList, searchQuery]);

  const isHeroAvailable = (heroId: number) => !usedHeroIds.includes(heroId);
  const matchesSearch = (heroId: number) =>
    filteredHeroes.some((h) => h.id === heroId);

  return (
    <div className="flex flex-col h-full">
      <div className="p-2">
        <Input
          type="text"
          placeholder="Search heroes..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full"
        />
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-4">
        {ATTRIBUTE_ORDER.map((attr) => (
          <div key={attr}>
            <h3 className="text-sm font-semibold mb-2 text-muted-foreground">
              {ATTRIBUTE_LABELS[attr]}
            </h3>
            <div className="grid grid-cols-8 gap-1">
              {heroList
                .filter((h) => h.attr === attr)
                .map((hero) => {
                  const available = isHeroAvailable(hero.id);
                  const matches = matchesSearch(hero.id);
                  const isSelected = selectedHeroId === hero.id;

                  return (
                    <button
                      key={hero.id}
                      onClick={() => {
                        if (!disabled && available) {
                          setSelectedHeroId(hero.id);
                          onHeroClick(hero.id);
                        }
                      }}
                      disabled={disabled || !available}
                      title={hero.name}
                      className={cn(
                        'relative aspect-[4/5] rounded overflow-hidden transition-all',
                        'hover:ring-2 hover:ring-primary',
                        isSelected && 'ring-2 ring-yellow-400',
                        !available && 'opacity-30',
                        !matches && searchQuery && 'grayscale opacity-50',
                        disabled && 'cursor-not-allowed'
                      )}
                    >
                      <img
                        src={hero.icon}
                        alt={hero.name}
                        className="w-full h-full object-cover"
                      />
                      {!available && (
                        <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
                          <span className="text-red-500 text-xs">✕</span>
                        </div>
                      )}
                    </button>
                  );
                })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
