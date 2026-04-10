import { useState } from 'react';
import { Badge } from '~/components/ui/badge';
import { InfoDialog } from '~/components/ui/dialogs';
import { ChevronDown, ChevronRight, ExternalLink } from 'lucide-react';

interface DiscordLogEntry {
  id: number;
  action: string;
  target_type: string;
  success: boolean;
  status_code?: number;
  message_id?: string;
  discord_user_id?: string;
  discord_username?: string;
  response_data?: Record<string, unknown>;
  error_message?: string;
  created_at: string;
  category?: number;
  category_display?: string;
}

interface DiscordLogDetailModalProps {
  log: DiscordLogEntry | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  repeaterName?: string;
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function DiscordLogDetailModal({
  log,
  open,
  onOpenChange,
  repeaterName,
}: DiscordLogDetailModalProps) {
  const [showRaw, setShowRaw] = useState(false);

  if (!log) return null;

  return (
    <InfoDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Discord Log Entry"
      data-testid="discord-log-detail-modal"
    >
      <div className="space-y-4">
        {/* Status + Action */}
        <div className="flex items-center gap-3">
          <Badge
            className={
              log.success
                ? 'bg-success/20 text-success border-success/30'
                : 'bg-destructive/20 text-error border-destructive/30'
            }
          >
            {log.success ? 'Success' : 'Failed'}
          </Badge>
          <span className="font-semibold text-foreground">{log.action}</span>
        </div>

        {/* Details grid */}
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="text-muted-foreground">Target</div>
          <div>{log.target_type}</div>

          <div className="text-muted-foreground">Timestamp</div>
          <div>
            {new Date(log.created_at).toLocaleString()}{' '}
            <span className="text-muted-foreground">({formatRelativeTime(log.created_at)})</span>
          </div>

          {log.status_code && (
            <>
              <div className="text-muted-foreground">HTTP Status</div>
              <div>{log.status_code}</div>
            </>
          )}

          {log.message_id && (
            <>
              <div className="text-muted-foreground">Message ID</div>
              <div className="flex items-center gap-1">
                <code className="text-xs bg-base-400 px-1 rounded">{log.message_id}</code>
              </div>
            </>
          )}

          {log.discord_username && (
            <>
              <div className="text-muted-foreground">Discord User</div>
              <div>{log.discord_username}</div>
            </>
          )}

          {repeaterName && (
            <>
              <div className="text-muted-foreground">Series</div>
              <div>{repeaterName}</div>
            </>
          )}

          {log.category_display && (
            <>
              <div className="text-muted-foreground">Category</div>
              <div>{log.category_display}</div>
            </>
          )}

          <div className="text-muted-foreground">Log ID</div>
          <div className="text-xs text-muted-foreground">#{log.id}</div>
        </div>

        {/* Error message */}
        {log.error_message && (
          <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-3">
            <div className="text-sm font-medium text-error mb-1">Error</div>
            <pre className="text-xs text-muted-foreground whitespace-pre-wrap">{log.error_message}</pre>
          </div>
        )}

        {/* Expandable raw data */}
        {log.response_data && (
          <div data-testid="discord-log-raw-data">
            <button
              type="button"
              className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
              onClick={() => setShowRaw(!showRaw)}
            >
              {showRaw ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              Raw Response Data
            </button>
            {showRaw && (
              <pre className="mt-2 p-3 bg-base-400 rounded-lg text-xs overflow-auto max-h-64 text-muted-foreground">
                {JSON.stringify(log.response_data, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    </InfoDialog>
  );
}
