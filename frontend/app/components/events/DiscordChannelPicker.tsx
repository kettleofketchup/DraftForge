import { RefreshCw, Volume2 } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
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
  kind?: 'text' | 'voice';
  'data-testid'?: string;
}

export function DiscordChannelPicker({
  organizationId,
  value,
  onChange,
  disabled,
  kind = 'text',
  'data-testid': testId,
}: DiscordChannelPickerProps) {
  const [channels, setChannels] = useState<DiscordChannel[]>([]);
  const [channelsKind, setChannelsKind] = useState(kind);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const latestRequest = useRef(0);

  if (channelsKind !== kind) {
    setChannelsKind(kind);
    setChannels([]);
  }

  const fetchChannels = useCallback(
    async (refresh = false) => {
      const request = ++latestRequest.current;
      setLoading(true);
      setError(null);
      try {
        const result = await getDiscordChannels(organizationId, refresh, kind);
        if (request === latestRequest.current) setChannels(result);
      } catch {
        if (request === latestRequest.current)
          setError('Failed to load channels');
      } finally {
        if (request === latestRequest.current) setLoading(false);
      }
    },
    [organizationId, kind],
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
        <SelectTrigger className="w-full min-w-0" data-testid={testId}>
          <SelectValue
            placeholder={loading ? 'Loading...' : 'Select channel'}
          />
        </SelectTrigger>
        <SelectContent>
          {error && (
            <div className="px-2 py-1.5 text-sm text-error">{error}</div>
          )}
          {channels.length === 0 && !error && !loading && (
            <div className="px-2 py-1.5 text-sm text-muted-foreground">
              No {kind} channels found
            </div>
          )}
          {channels.map((ch) => (
            <SelectItem key={ch.id} value={ch.id}>
              <span className="flex items-center gap-1.5">
                {kind === 'voice' ? (
                  <Volume2
                    className="h-3.5 w-3.5 text-muted-foreground"
                    aria-hidden="true"
                  />
                ) : (
                  <span className="text-muted-foreground">#</span>
                )}
                {ch.name}
                {ch.type_label !== kind && (
                  <span className="text-xs text-muted-foreground">
                    ({ch.type_label})
                  </span>
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
