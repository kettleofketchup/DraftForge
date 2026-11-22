import { useEffect } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '~/components/ui/card';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import {
  formatForecast,
  formatOpenSeats,
  formatPendingApproval,
} from './forecastFormat';
import { useForecast } from './queries';

const log = getLogger('ConductForecastCard');

export interface ConductForecastCardProps {
  orgId: number;
  eventId: number;
  access: OrgFeatureAccess;
}

export function ConductForecastCard({
  orgId,
  eventId,
  access,
}: ConductForecastCardProps) {
  const { data, isError, error } = useForecast(orgId, access, eventId, true);

  useEffect(() => {
    if (isError)
      log.error('conduct forecast failed to load', { orgId, eventId, error });
  }, [isError, error, orgId, eventId]);

  if (isError) {
    return (
      <Card data-testid="conduct-forecast">
        <CardHeader>
          <CardTitle>Turnout forecast</CardTitle>
          <CardDescription
            className="text-destructive"
            data-testid="conduct-forecast-error"
          >
            {extractApiError(error) ?? 'Could not load the turnout forecast.'}
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }
  if (!data) return null;
  const openSeats = formatOpenSeats(data);
  const pending = formatPendingApproval(data);

  return (
    <Card data-testid="conduct-forecast">
      <CardHeader>
        <CardTitle>Turnout forecast</CardTitle>
        <CardDescription data-testid="conduct-forecast-summary">
          {formatForecast(data)}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-1 text-sm text-muted-foreground sm:flex-row sm:flex-wrap sm:gap-x-4">
        {openSeats && (
          <span data-testid="conduct-forecast-open-seats">{openSeats}</span>
        )}
        <span data-testid="conduct-forecast-new-members">
          {data.new_members} new {data.new_members === 1 ? 'member' : 'members'}
        </span>
        {pending && (
          <span data-testid="conduct-forecast-pending-approval">{pending}</span>
        )}
      </CardContent>
    </Card>
  );
}
