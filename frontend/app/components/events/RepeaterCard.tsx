import { useNavigate } from 'react-router';
import { Calendar, Repeat, Users } from 'lucide-react';
import { Badge } from '~/components/ui/badge';
import { FREQUENCY_LABELS } from './schemas';

interface RepeaterCardProps {
  repeater: {
    id: number;
    name: string;
    organization: number;
    organization_name?: string;
    frequency: string;
    is_active: boolean;
    subscriber_count: number;
    next_event_date: string | null;
  };
}

export function RepeaterCard({ repeater }: RepeaterCardProps) {
  const navigate = useNavigate();

  return (
    <div
      data-testid={`repeater-card-${repeater.id}`}
      className="bg-base-300 border border-border rounded-lg p-4 hover:bg-base-400/30 transition-colors cursor-pointer"
      onClick={() => navigate(`/event-series/${repeater.id}`)}
    >
      <div className="flex items-start justify-between mb-2">
        <h3 className="text-foreground font-semibold text-sm truncate">{repeater.name}</h3>
        <Badge
          className={
            repeater.is_active
              ? 'bg-success/20 text-success border-success/30'
              : 'bg-muted text-muted-foreground border-border'
          }
        >
          {repeater.is_active ? 'Active' : 'Inactive'}
        </Badge>
      </div>

      {repeater.organization_name && (
        <p className="text-muted-foreground text-xs mb-3">{repeater.organization_name}</p>
      )}

      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <div className="flex items-center gap-1">
          <Repeat className="h-3 w-3" />
          <Badge className="bg-primary/20 text-primary border-primary/30 text-[10px]">
            {FREQUENCY_LABELS[repeater.frequency] || repeater.frequency}
          </Badge>
        </div>

        <div className="flex items-center gap-1">
          <Users className="h-3 w-3" />
          <span>{repeater.subscriber_count}</span>
        </div>

        {repeater.next_event_date && (
          <div className="flex items-center gap-1">
            <Calendar className="h-3 w-3" />
            <span>{new Date(repeater.next_event_date).toLocaleDateString()}</span>
          </div>
        )}
      </div>
    </div>
  );
}
