import { memo } from 'react';
import { Badge } from '~/components/ui/badge';

interface SwissBracketViewProps {
  tournamentId: number;
}

/**
 * Swiss bracket view - STUB for future implementation
 */
export const SwissBracketView = memo(({ tournamentId }: SwissBracketViewProps) => {
  return (
    <div className="flex flex-col items-center justify-center h-96 text-muted-foreground">
      <Badge variant="outline" className="mb-4">Coming Soon</Badge>
      <p>Swiss bracket view is not yet implemented.</p>
      <p className="text-sm mt-2">Tournament ID: {tournamentId}</p>
    </div>
  );
});

SwissBracketView.displayName = 'SwissBracketView';
