import {
  BrandSelect,
  BrandSelectContent,
  BrandSelectItem,
  BrandSelectTrigger,
  SelectValue,
} from '~/components/ui/brand-select';
import { ToggleGroup, ToggleGroupItem } from '~/components/ui/toggle-group';
import type { TrackInfo } from './schemas';

export const METRIC_TOGGLE_MAX = 3;

export interface MetricSwitcherProps {
  track: TrackInfo;
  value: string;
  onChange: (key: string) => void;
}

export function MetricSwitcher({
  track,
  value,
  onChange,
}: MetricSwitcherProps) {
  if (track.metrics.length < 2) return null;
  if (track.metrics.length > METRIC_TOGGLE_MAX) {
    return (
      <BrandSelect value={value} onValueChange={onChange}>
        <BrandSelectTrigger
          className="w-full sm:w-auto sm:min-w-44"
          aria-label="Metric"
          data-testid={`standing-metric-${track.key}`}
        >
          <SelectValue />
        </BrandSelectTrigger>
        <BrandSelectContent>
          {track.metrics.map((m) => (
            <BrandSelectItem
              key={m.key}
              value={m.key}
              data-testid={`standing-metric-${track.key}-${m.key}`}
            >
              {m.label}
            </BrandSelectItem>
          ))}
        </BrandSelectContent>
      </BrandSelect>
    );
  }
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      value={value}
      onValueChange={(next) => {
        if (next) onChange(next);
      }}
      aria-label="Metric"
      data-testid={`standing-metric-${track.key}`}
    >
      {track.metrics.map((m) => (
        <ToggleGroupItem
          key={m.key}
          value={m.key}
          className="px-3"
          data-testid={`standing-metric-${track.key}-${m.key}`}
        >
          {m.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
