import { RefreshCw } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { getDiscordChannels, type DiscordChannel } from '~/components/api/api';
import { Button } from '~/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';

interface DiscordChannelPickerProps {
  organizationId: number;
  value: string;
  onChange: (channelId: string) => void;
  disabled?: boolean;
  'data-testid'?: string;
}

export function DiscordChannelPicker({
  organizationId,
  value,
  onChange,
  disabled,
  'data-testid': testId,
}: DiscordChannelPickerProps) {
  const [channels, setChannels] = useState<DiscordChannel[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchChannels = useCallback(
    async (refresh = false) => {
      setLoading(true);
      setError(null);
      try {
        const result = await getDiscordChannels(organizationId, refresh);
        setChannels(result);
      } catch {
        setError('Failed to load channels');
      } finally {
        setLoading(false);
      }
    },
    [organizationId]
  );

  useEffect(() => {
    if (organizationId) fetchChannels();
  }, [organizationId, fetchChannels]);

  return (
    <div className="flex items-center gap-2">
      <Select
        value={value}
        onValueChange={onChange}
        disabled={disabled || loading}
      >
        <SelectTrigger className="w-full" data-testid={testId}>
          <SelectValue placeholder={loading ? 'Loading...' : 'Select channel'} />
        </SelectTrigger>
        <SelectContent>
          {error && (
            <div className="px-2 py-1.5 text-sm text-error">{error}</div>
          )}
          {channels.length === 0 && !error && !loading && (
            <div className="px-2 py-1.5 text-sm text-muted-foreground">No text channels found</div>
          )}
          {channels.map((ch) => (
            <SelectItem key={ch.id} value={ch.id}>
              <span className="flex items-center gap-1.5">
                <span className="text-muted-foreground">#</span>
                {ch.name}
                {ch.type_label !== 'text' && (
                  <span className="text-xs text-muted-foreground">({ch.type_label})</span>
                )}
              </span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="shrink-0"
        onClick={() => fetchChannels(true)}
        disabled={loading}
        title="Refresh channels"
      >
        <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
      </Button>
    </div>
  );
}
