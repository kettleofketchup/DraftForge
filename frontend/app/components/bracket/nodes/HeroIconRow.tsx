// frontend/app/components/bracket/nodes/HeroIconRow.tsx
import { getHeroIcon, getHeroName } from '~/lib/dota';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { cn } from '~/lib/utils';

interface HeroIconRowProps {
  heroIds: number[];
  isWinner?: boolean;
}

export function HeroIconRow({ heroIds, isWinner }: HeroIconRowProps) {
  return (
    <div
      className={cn('flex gap-0.5', isWinner && 'ring-1 ring-green-500 rounded')}
    >
      {heroIds.map((heroId, index) => (
        <Tooltip key={`${heroId}-${index}`}>
          <TooltipTrigger asChild>
            <img
              src={getHeroIcon(heroId)}
              alt={getHeroName(heroId)}
              className="w-5 h-5 rounded-sm"
            />
          </TooltipTrigger>
          <TooltipContent>{getHeroName(heroId)}</TooltipContent>
        </Tooltip>
      ))}
    </div>
  );
}
