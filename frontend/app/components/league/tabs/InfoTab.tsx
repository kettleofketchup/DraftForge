import { Award, Users, FileText } from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '~/components/ui/card';
import { Badge } from '~/components/ui/badge';
import { Avatar, AvatarImage, AvatarFallback } from '~/components/ui/avatar';
import { AvatarUrl } from '~/components/user/avatar';
import type { LeagueType } from '../schemas';

interface Props {
  league: LeagueType;
}

export const InfoTab: React.FC<Props> = ({ league }) => {
  return (
    <div className="space-y-6">
      {/* Prize Pool */}
      {league.prize_pool && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Award className="h-5 w-5" />
              Prize Pool
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{league.prize_pool}</p>
          </CardContent>
        </Card>
      )}

      {/* Description */}
      {league.description && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              About
            </CardTitle>
          </CardHeader>
          <CardContent className="prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap">
            {league.description}
          </CardContent>
        </Card>
      )}

      {/* Rules */}
      {league.rules && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Rules
            </CardTitle>
          </CardHeader>
          <CardContent className="prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap">
            {league.rules}
          </CardContent>
        </Card>
      )}

      {/* Admins */}
      {league.admins && league.admins.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              League Admins
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              {league.admins.map((admin) => (
                <div key={admin.pk} className="flex items-center gap-2">
                  <Avatar className="h-8 w-8">
                    <AvatarImage src={AvatarUrl(admin)} alt={admin.nickname || admin.username} />
                    <AvatarFallback>{(admin.nickname || admin.username).charAt(0).toUpperCase()}</AvatarFallback>
                  </Avatar>
                  <span className="text-sm">{admin.nickname || admin.username}</span>
                  <Badge variant="secondary" className="text-xs">Admin</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};
