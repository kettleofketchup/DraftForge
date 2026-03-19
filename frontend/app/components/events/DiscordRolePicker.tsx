import { RefreshCw } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { getDiscordRoles, type DiscordRole } from '~/components/api/api';
import { Button } from '~/components/ui/button';
import { Badge } from '~/components/ui/badge';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import { cn } from '~/lib/utils';

interface DiscordRolePickerProps {
  organizationId: number;
  value: string[];
  onChange: (roleIds: string[]) => void;
  disabled?: boolean;
}

export function DiscordRolePicker({
  organizationId,
  value,
  onChange,
  disabled,
}: DiscordRolePickerProps) {
  const [roles, setRoles] = useState<DiscordRole[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const fetchRoles = useCallback(
    async (refresh = false) => {
      setLoading(true);
      setError(null);
      try {
        const result = await getDiscordRoles(organizationId, refresh);
        setRoles(result);
      } catch {
        setError('Failed to load roles');
      } finally {
        setLoading(false);
      }
    },
    [organizationId]
  );

  useEffect(() => {
    if (organizationId) fetchRoles();
  }, [organizationId, fetchRoles]);

  const toggleRole = (roleId: string) => {
    if (value.includes(roleId)) {
      onChange(value.filter((id) => id !== roleId));
    } else {
      onChange([...value, roleId]);
    }
  };

  const selectedNames = roles
    .filter((r) => value.includes(r.id))
    .map((r) => r.name);

  return (
    <div className="flex items-center gap-2">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            className="w-full justify-start font-normal"
            disabled={disabled || loading}
          >
            {loading ? (
              'Loading...'
            ) : selectedNames.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {selectedNames.map((name) => (
                  <Badge key={name} variant="secondary" className="text-xs">
                    @{name}
                  </Badge>
                ))}
              </div>
            ) : (
              <span className="text-muted-foreground">Select roles to mention</span>
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-64 p-2" align="start">
          {error && (
            <div className="px-2 py-1.5 text-sm text-destructive">{error}</div>
          )}
          {roles.length === 0 && !error && !loading && (
            <div className="px-2 py-1.5 text-sm text-muted-foreground">
              No roles found
            </div>
          )}
          <div className="max-h-48 overflow-y-auto space-y-1">
            {roles
              .sort((a, b) => b.position - a.position)
              .map((role) => (
                <button
                  key={role.id}
                  type="button"
                  onClick={() => toggleRole(role.id)}
                  className={cn(
                    'w-full text-left px-2 py-1.5 rounded text-sm flex items-center gap-2 hover:bg-accent',
                    value.includes(role.id) && 'bg-accent'
                  )}
                >
                  <div
                    className="w-3 h-3 rounded-full shrink-0"
                    style={{
                      backgroundColor: role.color
                        ? `#${role.color.toString(16).padStart(6, '0')}`
                        : '#99aab5',
                    }}
                  />
                  <span>@{role.name}</span>
                  {value.includes(role.id) && (
                    <span className="ml-auto text-xs text-muted-foreground">&#10003;</span>
                  )}
                </button>
              ))}
          </div>
        </PopoverContent>
      </Popover>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="shrink-0"
        onClick={() => fetchRoles(true)}
        disabled={loading}
        title="Refresh roles"
      >
        <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
      </Button>
    </div>
  );
}
