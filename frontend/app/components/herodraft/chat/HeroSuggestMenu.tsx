import { Ban, ThumbsUp } from 'lucide-react';
import { type MouseEvent, type ReactElement, useState } from 'react';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuLabel,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '~/components/ui/context-menu';
import { getHeroIcon, getHeroName } from '~/lib/dota/heroes';
import type { HeroSuggestionKind } from '~/store/heroDraftStore';

interface SuggestTarget {
  heroId: number;
  available: boolean;
}

export interface HeroSuggestMenuProps {
  onSuggest: (kind: HeroSuggestionKind, heroId: number) => void;
  children: ReactElement;
}

export function HeroSuggestMenu({ onSuggest, children }: HeroSuggestMenuProps) {
  const [target, setTarget] = useState<SuggestTarget | null>(null);

  const onContextMenu = (e: MouseEvent<HTMLElement>) => {
    const el = (e.target as Element).closest<HTMLElement>('[data-hero-id]');
    const heroId = Number(el?.dataset.heroId);
    if (!el || !Number.isInteger(heroId)) {
      e.preventDefault();
      return;
    }
    setTarget({ heroId, available: el.dataset.heroAvailable === 'true' });
  };

  const disabled = !target?.available;

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild onContextMenu={onContextMenu}>
        {children}
      </ContextMenuTrigger>
      {target && (
        <ContextMenuContent
          className="w-48"
          data-testid="herodraft-hero-suggest-menu"
        >
          <ContextMenuLabel className="flex items-center gap-2">
            <img
              src={getHeroIcon(target.heroId)}
              alt=""
              className="size-5 rounded-full object-cover"
            />
            <span className="truncate">{getHeroName(target.heroId)}</span>
          </ContextMenuLabel>
          <ContextMenuSeparator />
          <ContextMenuItem
            disabled={disabled}
            onSelect={() => onSuggest('suggest_pick', target.heroId)}
            data-testid="herodraft-hero-suggest-pick"
          >
            <ThumbsUp className="size-4 text-pick" />
            Suggest pick
          </ContextMenuItem>
          <ContextMenuItem
            disabled={disabled}
            onSelect={() => onSuggest('suggest_ban', target.heroId)}
            data-testid="herodraft-hero-suggest-ban"
          >
            <Ban className="size-4 text-ban" />
            Suggest ban
          </ContextMenuItem>
        </ContextMenuContent>
      )}
    </ContextMenu>
  );
}
