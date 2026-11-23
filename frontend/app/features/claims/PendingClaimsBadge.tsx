import { Badge } from '~/components/ui/badge';

export function PendingClaimsBadge({
  count,
  testId,
}: {
  count: number;
  testId: string;
}) {
  if (count <= 0) return null;
  return (
    <Badge variant="secondary" className="ml-1 text-xs" data-testid={testId}>
      {count}
    </Badge>
  );
}
