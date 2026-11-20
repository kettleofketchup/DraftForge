import { Building2, ChevronRight } from 'lucide-react';
import { useCallback, useState } from 'react';
import { Link } from 'react-router';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import type { OrganizationType } from './schemas';

interface OrganizationPopoverProps {
  organization: OrganizationType;
  children: React.ReactNode;
}

export function OrganizationPopover({
  organization,
  children,
}: OrganizationPopoverProps) {
  const [open, setOpen] = useState(false);

  const handleMouseEnter = useCallback(() => setOpen(true), []);
  const handleMouseLeave = useCallback(() => setOpen(false), []);
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        setOpen((prev) => !prev);
      } else if (e.key === 'Escape') {
        setOpen(false);
      }
    },
    [],
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        asChild
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        onKeyDown={handleKeyDown}
        role="button"
        tabIndex={0}
        aria-expanded={open}
        aria-label={`View details for ${organization.name}`}
      >
        {children}
      </PopoverTrigger>
      <PopoverContent
        className="w-80"
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-3">
            {organization.logo ? (
              <img
                src={organization.logo}
                alt={organization.name}
                className="w-10 h-10 rounded-lg object-cover"
              />
            ) : (
              <div className="w-10 h-10 rounded-lg bg-muted flex items-center justify-center">
                <Building2 className="w-5 h-5 text-muted-foreground" />
              </div>
            )}
            <div>
              <h4 className="font-semibold">{organization.name}</h4>
              <p className="text-sm text-muted-foreground">
                {organization.league_count} leagues &middot;{' '}
                {organization.tournament_count} tournaments
              </p>
            </div>
          </div>

          {organization.description && (
            <p className="text-sm text-muted-foreground line-clamp-3">
              {organization.description}
            </p>
          )}

          <Link
            to={`/organizations/${organization.pk}`}
            className="flex items-center justify-between text-sm text-primary hover:underline"
          >
            View Organization
            <ChevronRight className="w-4 h-4" />
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  );
}
