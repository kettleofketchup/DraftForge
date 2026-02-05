import React, { useCallback, useState } from 'react';
import { Button } from '~/components/ui/button';
import { Badge } from '~/components/ui/badge';
import { UserStrip } from '~/components/user/UserStrip';
import { toast } from 'sonner';
import type { SearchUserResult, AddMemberPayload } from '~/components/api/api';
import type { SiteUserResultsProps } from './types';

function MembershipBadge({ result }: { result: SearchUserResult }) {
  if (!result.membership) return null;

  const config: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline'; className: string }> = {
    league: { label: 'League Member', variant: 'secondary', className: 'text-info' },
    org: { label: 'Org Member', variant: 'secondary', className: 'text-success' },
    other_org: { label: `Other: ${result.membership_label}`, variant: 'outline', className: 'text-warning' },
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

export const SiteUserResults: React.FC<SiteUserResultsProps> = ({
  results,
  loading,
  onAdd,
  isAdded,
  entityLabel,
}) => {
  const [addingPk, setAddingPk] = useState<number | null>(null);

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

  if (results.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        No site users found
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      {results.map((result) => {
        const added = result.pk ? isAdded(result) : false;

        return (
          <UserStrip
            key={result.pk}
            user={result}
            compact
            contextSlot={<MembershipBadge result={result} />}
            actionSlot={
              added ? (
                <span className="text-xs text-muted-foreground">
                  Already in {entityLabel}
                </span>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleAdd(result)}
                  disabled={addingPk === result.pk}
                  data-testid={`add-user-btn-${result.username}`}
                >
                  {addingPk === result.pk ? '...' : '+'}
                </Button>
              )
            }
            className={added ? 'opacity-50' : ''}
          />
        );
      })}
    </div>
  );
};
