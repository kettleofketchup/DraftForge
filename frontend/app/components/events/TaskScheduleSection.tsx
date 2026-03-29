import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Play } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '~/components/ui/badge';
import { Button } from '~/components/ui/button';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { UserAvatar } from '~/components/user/UserAvatar';
import api from '~/components/api/axios';
import { useUserStore } from '~/store/userStore';

interface FiredByUser {
  pk: number;
  username: string;
  nickname: string | null;
  discordId: string | null;
  avatar: string | null;
}

interface TaskEntry {
  task: string;
  label: string;
  fires_at: string | null;
  status: 'fired' | 'pending' | 'ready' | 'disabled' | 'misconfigured';
  description: string;
  check_interval: string | null;
  last_fired_at: string | null;
  fired_by: FiredByUser | null;
  can_fire: boolean;
}

function useEventTaskSchedule(eventId: number | null) {
  return useQuery<TaskEntry[]>({
    queryKey: ['event-task-schedule', eventId],
    queryFn: () => api.get(`/events/${eventId}/task-schedule/`).then((r) => r.data),
    enabled: !!eventId,
  });
}

const STATUS_EMOJI: Record<string, string> = {
  fired: '✅',
  pending: '⏳',
  ready: '🔵',
  disabled: '⚫',
  misconfigured: '⚠️',
};

const STATUS_BADGE: Record<string, string> = {
  fired: 'bg-success/20 text-success border-success/30',
  pending: 'bg-warning/20 text-warning border-warning/30',
  ready: 'bg-info/20 text-info border-info/30',
  disabled: 'bg-muted text-muted-foreground border-border',
  misconfigured: 'bg-destructive/20 text-error border-destructive/30',
};

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diff = date.getTime() - now.getTime();
  const absDiff = Math.abs(diff);
  const mins = Math.floor(absDiff / 60000);
  const hours = Math.floor(mins / 60);
  const days = Math.floor(hours / 24);

  const prefix = diff > 0 ? 'in ' : '';
  const suffix = diff > 0 ? '' : ' ago';

  if (mins < 1) return 'now';
  if (mins < 60) return `${prefix}${mins}m${suffix}`;
  if (hours < 24) return `${prefix}${hours}h ${mins % 60}m${suffix}`;
  return `${prefix}${days}d ${hours % 24}h${suffix}`;
}

interface TaskScheduleSectionProps {
  eventId: number;
  isAdmin?: boolean;
  eventTimezone?: string;
}

export function TaskScheduleSection({ eventId, isAdmin, eventTimezone }: TaskScheduleSectionProps) {
  const { data: tasks, isLoading } = useEventTaskSchedule(eventId);
  const queryClient = useQueryClient();
  const currentUser = useUserStore((state) => state.currentUser);
  const [confirmTask, setConfirmTask] = useState<TaskEntry | null>(null);
  // Site staff can always fire, plus explicit isAdmin prop
  const canFire = isAdmin || currentUser?.is_staff || currentUser?.is_superuser;

  const fireMutation = useMutation({
    mutationFn: (taskName: string) =>
      api.post(`/events/${eventId}/task-schedule/${taskName}/fire/`),
    onSuccess: (_data, taskName) => {
      toast.success(`Task "${taskName}" fired`);
      queryClient.invalidateQueries({ queryKey: ['event-task-schedule', eventId] });
      queryClient.invalidateQueries({ queryKey: ['event-discord', eventId] });
    },
    onError: (err: any, taskName) => {
      const msg = err?.response?.data?.error || err.message;
      if (err?.response?.status === 409) {
        toast.warning(msg);
      } else {
        toast.error(`Failed to fire "${taskName}": ${msg}`);
      }
    },
  });

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

  // Sort: fired first, then ready/pending, disabled last
  const sorted = [...tasks].sort((a, b) => {
    const order = { fired: 0, ready: 1, pending: 2, misconfigured: 3, disabled: 4 };
    const aOrder = order[a.status] ?? 5;
    const bOrder = order[b.status] ?? 5;
    if (aOrder !== bOrder) return aOrder - bOrder;
    if (a.fires_at && b.fires_at) return new Date(a.fires_at).getTime() - new Date(b.fires_at).getTime();
    return 0;
  });

  return (
    <div data-testid="task-schedule-section">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs text-muted-foreground border-b border-border/50">
            <th className="text-left py-2 pl-1 w-8"></th>
            <th className="text-left py-2">Task</th>
            <th className="text-left py-2 hidden sm:table-cell">Timing</th>
            <th className="text-left py-2 hidden md:table-cell">Check</th>
            <th className="text-left py-2">Status</th>
            <th className="text-left py-2 hidden lg:table-cell">Fired By</th>
            {canFire && <th className="text-right py-2 pr-1 w-16"></th>}
          </tr>
        </thead>
        <tbody>
          {sorted.map((task) => (
            <tr
              key={task.task}
              data-testid={`task-schedule-entry-${task.task}`}
              className={`border-b border-border/20 hover:bg-base-400/10 transition-colors ${
                task.status === 'disabled' ? 'opacity-50' : ''
              }`}
            >
              {/* Status emoji */}
              <td className="py-2.5 pl-1 text-center">
                <span title={task.status}>{STATUS_EMOJI[task.status] || '❓'}</span>
              </td>

              {/* Task name + description */}
              <td className="py-2.5">
                <div className="font-medium text-foreground">{task.label}</div>
                {task.description && (
                  <div className="text-xs text-muted-foreground mt-0.5">{task.description}</div>
                )}
              </td>

              {/* Timing — fires_at or last_fired_at */}
              <td className="py-2.5 hidden sm:table-cell">
                {task.fires_at ? (
                  <div>
                    <div className="text-foreground">{formatRelativeTime(task.fires_at)}</div>
                    <div className="text-[10px] text-muted-foreground">
                      {new Date(task.fires_at).toLocaleString(undefined, {
                        timeZone: eventTimezone || undefined,
                        month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
                        timeZoneName: 'short',
                      })}
                    </div>
                  </div>
                ) : task.last_fired_at ? (
                  <div className="text-xs text-muted-foreground">
                    Last: {formatRelativeTime(task.last_fired_at)}
                  </div>
                ) : task.status === 'disabled' ? (
                  <span className="text-muted-foreground">—</span>
                ) : (
                  <span className="text-muted-foreground text-xs">On trigger</span>
                )}
              </td>

              {/* Check interval */}
              <td className="py-2.5 hidden md:table-cell">
                {task.check_interval ? (
                  <span className="text-xs text-muted-foreground">{task.check_interval}</span>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </td>

              {/* Status badge */}
              <td className="py-2.5">
                <Badge className={`text-xs ${STATUS_BADGE[task.status] || ''}`}>
                  {task.status.charAt(0).toUpperCase() + task.status.slice(1)}
                </Badge>
              </td>

              {/* Fired by */}
              <td className="py-2.5 hidden lg:table-cell">
                {task.fired_by ? (
                  <div className="flex items-center gap-1.5">
                    <UserAvatar
                      user={{
                        nickname: task.fired_by.nickname,
                        username: task.fired_by.username,
                        discordId: task.fired_by.discordId,
                        avatar: task.fired_by.avatar,
                      }}
                      size="xs"
                    />
                    <span className="text-xs text-foreground truncate max-w-[100px]">
                      {task.fired_by.nickname || task.fired_by.username}
                    </span>
                  </div>
                ) : task.status === 'fired' ? (
                  <span className="text-xs text-muted-foreground">Auto</span>
                ) : null}
              </td>

              {/* Fire button (admin only) */}
              {canFire && (
                <td className="py-2.5 text-right pr-1">
                  {task.can_fire && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0"
                      onClick={() => setConfirmTask(task)}
                      disabled={fireMutation.isPending}
                      title={`Fire ${task.label} now`}
                      data-testid={`fire-task-${task.task}`}
                    >
                      <Play className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>

      <ConfirmDialog
        open={!!confirmTask}
        onOpenChange={(open) => !open && setConfirmTask(null)}
        title={`Fire ${confirmTask?.label}?`}
        description={`This will immediately execute "${confirmTask?.label}" for this event. This action cannot be undone.`}
        confirmLabel="Fire Now"
        variant="default"
        onConfirm={() => {
          if (confirmTask) {
            fireMutation.mutate(confirmTask.task);
            setConfirmTask(null);
          }
        }}
      />
    </div>
  );
}
