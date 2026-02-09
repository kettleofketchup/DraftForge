import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Badge } from '~/components/ui/badge';
import { ConfirmButton } from '~/components/ui/buttons';
import { ScrollArea } from '~/components/ui/scroll-area';
import { UserStrip } from '~/components/user/UserStrip';
import { cn } from '~/lib/utils';
import { toast } from 'sonner';
import type { SearchUserResult } from '~/components/api/api';
import type { SiteUserResultsProps } from './types';

function MembershipBadge({ result }: { result: SearchUserResult }) {
  if (!result.membership) return null;

  const config: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline'; className: string }> = {
    league: { label: 'League Member', variant: 'outline', className: 'border-info text-info' },
    org: { label: 'Org Member', variant: 'outline', className: 'border-success text-success' },
    other_org: { label: `Other: ${result.membership_label}`, variant: 'outline', className: 'border-warning text-warning' },
  };

  const { label, variant, className } = config[result.membership] ?? {
    label: result.membership_label ?? '',
    variant: 'outline' as const,
    className: 'text-muted-foreground',
  };

  return (
    <Badge variant={variant} className={`text-xs px-1.5 py-0 ${className}`}>
      {label}
    </Badge>
  );
}

const MIN_QUERY_LENGTH = 3;

export const SiteUserResults: React.FC<SiteUserResultsProps> = ({
  results,
  loading,
  onAdd,
  isAdded,
  queryLength,
  highlightedIndex,
  showMembership = true,
}) => {
  const [addingPk, setAddingPk] = useState<number | null>(null);
  const itemRefs = useRef<(HTMLDivElement | null)[]>([]);

  // Scroll highlighted item into view
  useEffect(() => {
    if (highlightedIndex >= 0 && itemRefs.current[highlightedIndex]) {
      itemRefs.current[highlightedIndex]?.scrollIntoView({
        block: 'nearest',
      });
    }
  }, [highlightedIndex]);

  const handleAdd = useCallback(
    async (user: SearchUserResult) => {
      if (!user.pk) return;
      setAddingPk(user.pk);
      try {
        await onAdd({ user_id: user.pk });
        toast.success(`Added ${user.nickname || user.username}`);
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : 'Failed to add user'
        );
      } finally {
        setAddingPk(null);
      }
    },
    [onAdd]
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8 text-muted-foreground">
        Searching...
      </div>
    );
  }

  if (queryLength < MIN_QUERY_LENGTH) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        Type at least {MIN_QUERY_LENGTH} characters to search
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        No site users found
      </div>
    );
  }

  return (
    <ScrollArea className="h-96">
      <div className="flex flex-col gap-1 p-1 pr-4">
        {results.map((result, index) => {
          const added = result.pk ? isAdded(result) : false;
          const highlighted = index === highlightedIndex;

          return (
            <div
              key={result.pk}
              ref={(el) => { itemRefs.current[index] = el; }}
              className={cn(
                'rounded-lg',
                highlighted && 'ring-2 ring-primary ring-offset-1 ring-offset-background',
              )}
            >
              <UserStrip
                user={result}
                data-testid={`site-user-result-${result.username}`}
                compact
                showPositions={false}
                contextSlot={showMembership ? <MembershipBadge result={result} /> : undefined}
                actionSlot={
                  added ? (
                    <span className="text-xs text-muted-foreground">
                      Already added
                    </span>
                  ) : (
                    <ConfirmButton
                      variant="success"
                      size="sm"
                      depth={false}
                      onClick={() => handleAdd(result)}
                      loading={addingPk === result.pk}
                      data-testid={`add-user-btn-${result.username}`}
                    >
                      +
                    </ConfirmButton>
                  )
                }
                className={added ? 'opacity-50' : ''}
              />
            </div>
          );
        })}
      </div>
    </ScrollArea>
  );
};
