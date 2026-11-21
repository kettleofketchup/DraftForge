import { Info } from 'lucide-react';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';

const POINTS = [
  'An attended event counts as a full show and a no-show as a miss.',
  'A late cancel counts as half a miss by default.',
  'Excused, pending and voided outcomes, and walk-ins, are left out.',
  'Older events weigh less, and very old events are ignored.',
  "New members lean on the organization's baseline until they have a few counted events.",
];

export function ConductRateExplainer() {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <SecondaryButton
          size="icon"
          className="h-8 w-8"
          aria-label="How the show rate works"
          data-testid="conduct-rate-explainer"
        >
          <Info className="h-4 w-4" />
        </SecondaryButton>
      </PopoverTrigger>
      <PopoverContent
        className="w-80 text-sm"
        align="end"
        data-testid="conduct-rate-explainer-content"
      >
        <p className="mb-2 font-semibold">How the show rate works</p>
        <p className="mb-2 text-muted-foreground">
          The show rate is the share of recent events a member showed up to.
        </p>
        <ul className="list-disc space-y-1 pl-4 text-muted-foreground">
          {POINTS.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
