import { Building2 } from 'lucide-react';
import { Link } from 'react-router';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '~/components/ui/card';
import type { OrganizationType } from './schemas';

interface OrganizationCardProps {
  organization: OrganizationType;
}

export function OrganizationCard({ organization }: OrganizationCardProps) {
  return (
    <Link to={`/organizations/${organization.pk}`}>
      <Card className="hover:bg-accent transition-colors cursor-pointer">
        <CardHeader className="flex flex-row items-center gap-4">
          {organization.logo ? (
            <img
              src={organization.logo}
              alt={organization.name}
              className="w-12 h-12 rounded-lg object-cover"
            />
          ) : (
            <div className="w-12 h-12 rounded-lg bg-muted flex items-center justify-center">
              <Building2 className="w-6 h-6 text-muted-foreground" />
            </div>
          )}
          <div>
            <CardTitle className="text-lg">{organization.name}</CardTitle>
            <CardDescription>
              {organization.league_count} league
              {organization.league_count !== 1 ? 's' : ''}
            </CardDescription>
          </div>
        </CardHeader>
        {organization.description && (
          <CardContent>
            <p className="text-sm text-muted-foreground line-clamp-2">
              {organization.description}
            </p>
          </CardContent>
        )}
      </Card>
    </Link>
  );
}
