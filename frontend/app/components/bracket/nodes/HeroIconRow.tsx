// frontend/app/components/bracket/nodes/HeroIconRow.tsx
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { getHeroIcon, getHeroName } from '~/lib/dota';
import { cn } from '~/lib/utils';

interface HeroIconRowProps {
  heroIds: number[];
  isWinner?: boolean;
}

export function HeroIconRow({ heroIds, isWinner }: HeroIconRowProps) {
  return (
    <div
      className={cn('flex gap-0.5', isWinner && 'ring-1 ring-success rounded')}
    >
      {heroIds.map((heroId, index) => (
        <Tooltip key={`${heroId}-${index}`}>
          <TooltipTrigger asChild>
            <img
              src={getHeroIcon(heroId)}
              alt={getHeroName(heroId)}
              className="size-5 rounded-sm"
            />
          </TooltipTrigger>
          <TooltipContent>{getHeroName(heroId)}</TooltipContent>
        </Tooltip>
      ))}
    </div>
  );
}
