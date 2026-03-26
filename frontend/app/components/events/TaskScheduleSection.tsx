import { useQuery } from '@tanstack/react-query';
import { AlertCircle, CheckCircle, Circle, Clock, XCircle } from 'lucide-react';
import { Badge } from '~/components/ui/badge';
import api from '~/components/api/axios';

interface TaskEntry {
  task: string;
  label: string;
  fires_at: string | null;
  status: 'fired' | 'pending' | 'ready' | 'disabled' | 'misconfigured';
}

function useEventTaskSchedule(eventId: number | null) {
  return useQuery<TaskEntry[]>({
    queryKey: ['event-task-schedule', eventId],
    queryFn: () => api.get(`/events/${eventId}/task-schedule/`).then((r) => r.data),
    enabled: !!eventId,
  });
}

const STATUS_CONFIG = {
  fired: {
    icon: CheckCircle,
    badge: 'bg-success/20 text-success border-success/30',
    label: 'Fired',
  },
  pending: {
    icon: Clock,
    badge: 'bg-warning/20 text-warning border-warning/30',
    label: 'Pending',
  },
  ready: {
    icon: AlertCircle,
    badge: 'bg-info/20 text-info border-info/30',
    label: 'Ready',
  },
  disabled: {
    icon: Circle,
    badge: 'bg-muted text-muted-foreground border-border',
    label: 'Disabled',
  },
  misconfigured: {
    icon: XCircle,
    badge: 'bg-destructive/20 text-error border-destructive/30',
    label: 'Misconfigured',
  },
} as const;

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diff = date.getTime() - now.getTime();
  const absDiff = Math.abs(diff);
  const mins = Math.floor(absDiff / 60000);
  const hours = Math.floor(mins / 60);
  const days = Math.floor(hours / 24);

  const suffix = diff > 0 ? '' : ' ago';
  const prefix = diff > 0 ? 'in ' : '';

  if (mins < 1) return 'now';
  if (mins < 60) return `${prefix}${mins}m${suffix}`;
  if (hours < 24) return `${prefix}${hours}h${suffix}`;
  return `${prefix}${days}d${suffix}`;
}

interface TaskScheduleSectionProps {
  eventId: number;
}

export function TaskScheduleSection({ eventId }: TaskScheduleSectionProps) {
  const { data: tasks, isLoading } = useEventTaskSchedule(eventId);

  if (isLoading) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        Loading task schedule...
      </div>
    );
  }

  if (!tasks || tasks.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        No tasks configured for this event.
      </div>
    );
  }

  // Sort: fired first, then by fires_at (soonest first), disabled last
  const sorted = [...tasks].sort((a, b) => {
    const order = { fired: 0, ready: 1, pending: 2, misconfigured: 3, disabled: 4 };
    const aOrder = order[a.status] ?? 5;
    const bOrder = order[b.status] ?? 5;
    if (aOrder !== bOrder) return aOrder - bOrder;
    if (a.fires_at && b.fires_at) return new Date(a.fires_at).getTime() - new Date(b.fires_at).getTime();
    if (a.fires_at) return -1;
    if (b.fires_at) return 1;
    return 0;
  });

  return (
    <div className="space-y-1" data-testid="task-schedule-section">
      {sorted.map((task) => {
        const config = STATUS_CONFIG[task.status];
        const Icon = config.icon;

        return (
          <div
            key={task.task}
            data-testid={`task-schedule-entry-${task.task}`}
            className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-base-400/20 transition-colors"
          >
            <Icon className={`h-4 w-4 shrink-0 ${
              task.status === 'fired' ? 'text-success' :
              task.status === 'pending' ? 'text-warning' :
              task.status === 'ready' ? 'text-info' :
              task.status === 'misconfigured' ? 'text-error' :
              'text-muted-foreground'
            }`} />

            <div className="flex-1 min-w-0">
              <span className={`text-sm font-medium ${
                task.status === 'disabled' ? 'text-muted-foreground' : 'text-foreground'
              }`}>
                {task.label}
              </span>
            </div>

            {task.fires_at && task.status !== 'disabled' && (
              <span className="text-xs text-muted-foreground shrink-0">
                {formatRelativeTime(task.fires_at)}
              </span>
            )}

            <Badge className={`text-xs shrink-0 ${config.badge}`}>
              {config.label}
            </Badge>
          </div>
        );
      })}
    </div>
  );
}
