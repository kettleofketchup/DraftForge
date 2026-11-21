import { ToggleGroup, ToggleGroupItem } from '~/components/ui/toggle-group';
import type { TrackInfo } from './schemas';

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
