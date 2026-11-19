import { useEffect } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '~/components/ui/card';
import type { OrgFeatureAccess } from '~/features/org-features';
import { getLogger } from '~/lib/logger';
import { useForecast } from './queries';
import { formatForecast, formatOpenSeats } from './scoring';

const log = getLogger('ConductForecastCard');

export interface ConductForecastCardProps {
  orgId: number;
  eventId: number;
  access: OrgFeatureAccess;
  enabled?: boolean;
}

export function ConductForecastCard({
  orgId,
  eventId,
  access,
  enabled = true,
}: ConductForecastCardProps) {
  const { data, isError, error } = useForecast(orgId, access, eventId, enabled);

  useEffect(() => {
    if (isError)
      log.error('conduct forecast failed to load', { orgId, eventId, error });
  }, [isError, error, orgId, eventId]);

  if (!data) return null;
  const openSeats = formatOpenSeats(data);

  return (
    <Card data-testid="conduct-forecast">
      <CardHeader>
        <CardTitle>Turnout forecast</CardTitle>
        <CardDescription data-testid="conduct-forecast-summary">
          {formatForecast(data)}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
        {openSeats && (
          <span data-testid="conduct-forecast-open-seats">{openSeats}</span>
        )}
        <span data-testid="conduct-forecast-new-members">
          {data.new_members} new {data.new_members === 1 ? 'member' : 'members'}
        </span>
        {data.pending_approval > 0 && (
          <span data-testid="conduct-forecast-pending-approval">
            {data.pending_approval} awaiting approval
          </span>
        )}
      </CardContent>
    </Card>
  );
}
