import { Ban, ThumbsUp, X } from 'lucide-react';
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
  /** Off keeps the browser's own menu; the trigger stays mounted either way. */
  enabled: boolean;
  onSuggest: (kind: HeroSuggestionKind, heroId: number) => void;
  onUnsuggest?: (kind: HeroSuggestionKind, heroId: number) => void;
  /** Which of the viewer's own suggestions are live on a hero. */
  ownSuggestions?: (heroId: number) => { pick: boolean; ban: boolean };
  children: ReactElement;
}

const NONE = { pick: false, ban: false };

export function HeroSuggestMenu({
  enabled,
  onSuggest,
  onUnsuggest,
  ownSuggestions,
  children,
}: HeroSuggestMenuProps) {
  const [target, setTarget] = useState<SuggestTarget | null>(null);
  // Radix stays open through a disable; without this the old menu reappears.
  const [wasEnabled, setWasEnabled] = useState(enabled);
  if (wasEnabled !== enabled) {
    setWasEnabled(enabled);
    if (!enabled) setTarget(null);
  }

  const onContextMenu = (e: MouseEvent<HTMLElement>) => {
    if (!enabled) return;
    const el = (e.target as Element).closest<HTMLElement>('[data-hero-id]');
    const heroId = Number(el?.dataset.heroId);
    if (!el || !Number.isInteger(heroId)) {
      e.preventDefault();
      return;
    }
    setTarget({ heroId, available: el.dataset.heroAvailable === 'true' });
  };

  const disabled = !target?.available;
  const mine =
    target && onUnsuggest && ownSuggestions
      ? ownSuggestions(target.heroId)
      : NONE;

  return (
    <ContextMenu>
      <ContextMenuTrigger
        asChild
        disabled={!enabled}
        onContextMenu={onContextMenu}
      >
        {children}
      </ContextMenuTrigger>
      {enabled && target && (
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
          {mine.pick ? (
            <ContextMenuItem
              disabled={disabled}
              onSelect={() => onUnsuggest?.('suggest_pick', target.heroId)}
              data-testid="herodraft-hero-unsuggest-pick"
            >
              <X className="size-4 text-pick" />
              Remove pick suggestion
            </ContextMenuItem>
          ) : (
            <ContextMenuItem
              disabled={disabled}
              onSelect={() => onSuggest('suggest_pick', target.heroId)}
              data-testid="herodraft-hero-suggest-pick"
            >
              <ThumbsUp className="size-4 text-pick" />
              Suggest pick
            </ContextMenuItem>
          )}
          {mine.ban ? (
            <ContextMenuItem
              disabled={disabled}
              onSelect={() => onUnsuggest?.('suggest_ban', target.heroId)}
              data-testid="herodraft-hero-unsuggest-ban"
            >
              <X className="size-4 text-ban" />
              Remove ban suggestion
            </ContextMenuItem>
          ) : (
            <ContextMenuItem
              disabled={disabled}
              onSelect={() => onSuggest('suggest_ban', target.heroId)}
              data-testid="herodraft-hero-suggest-ban"
            >
              <Ban className="size-4 text-ban" />
              Suggest ban
            </ContextMenuItem>
          )}
        </ContextMenuContent>
      )}
    </ContextMenu>
  );
}
