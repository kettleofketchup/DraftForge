import { useEffect, useState } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { ExternalLink, Trophy, Users, Gamepad2, Award } from 'lucide-react';

import { fetchUser } from '~/components/api/api';
import { Tabs, TabsContent, TabsList, TabsTrigger, useUrlTabs } from '~/components/ui/tabs';
import { EditIconButton } from '~/components/ui/buttons';
import { Badge } from '~/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '~/components/ui/card';
import { ScrollArea, ScrollBar } from '~/components/ui/scroll-area';
import { Skeleton } from '~/components/ui/skeleton';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import { UserAvatar } from '~/components/user/UserAvatar';
import { RolePositions } from '~/components/user/positions';
import { EditProfileModal } from './EditProfileModal';
import { getLogger } from '~/lib/logger';

const log = getLogger('UserProfilePage');

export function UserProfilePage() {
  const { pk } = useParams<{ pk: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const currentUser = useUserStore((state) => state.currentUser);

  const [activeTab, setActiveTab] = useUrlTabs('overview', 'tab');
  const [editModalOpen, setEditModalOpen] = useState(false);

  // Check if edit modal should open (from /edit-profile redirect)
  useEffect(() => {
    if (searchParams.get('edit') === 'true') {
      setEditModalOpen(true);
      // Clean up URL but preserve tab
      const tab = searchParams.get('tab');
      navigate(`/user/${pk}${tab ? `?tab=${tab}` : ''}`, { replace: true });
    }
  }, [searchParams, pk, navigate]);

  const userId = pk ? parseInt(pk, 10) : null;
  const isOwnProfile = currentUser?.pk === userId;

  const { data: user, isLoading, error, refetch } = useQuery({
    queryKey: ['user', userId],
    queryFn: () => fetchUser(userId!),
    enabled: !!userId,
  });

  if (isLoading) {
    return <ProfileSkeleton />;
  }

  if (error || !user) {
    return (
      <div className="container mx-auto p-4">
        <div className="flex flex-col items-center justify-center h-64">
          <p className="text-muted-foreground">User not found</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-4 max-w-4xl">
      {/* Profile Header */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <Card className="mb-6">
          <CardContent className="pt-6">
            <div className="flex flex-col sm:flex-row gap-6 items-center sm:items-start">
              {/* Avatar */}
              <div className="relative">
                <UserAvatar
                  user={user}
                  size="xl"
                  border="primary"
                  className="w-24 h-24 sm:w-32 sm:h-32 shadow-lg"
                />
                {(user.is_staff || user.is_superuser) && (
                  <div className="absolute -bottom-2 left-1/2 -translate-x-1/2 flex gap-1">
                    {user.is_superuser && (
                      <Badge className="bg-red-600 text-white text-xs">Admin</Badge>
                    )}
                    {user.is_staff && !user.is_superuser && (
                      <Badge className="bg-blue-600 text-white text-xs">Staff</Badge>
                    )}
                  </div>
                )}
              </div>

              {/* User Info */}
              <div className="flex-1 text-center sm:text-left">
                <div className="flex flex-col sm:flex-row sm:items-center gap-2 mb-2">
                  <h1 className="text-2xl sm:text-3xl font-bold">
                    {user.nickname || user.username}
                  </h1>
                  {isOwnProfile && (
                    <EditIconButton
                      onClick={() => setEditModalOpen(true)}
                      tooltip="Edit Profile"
                      className="self-center sm:self-auto"
                    />
                  )}
                </div>

                {user.nickname && user.nickname !== user.username && (
                  <p className="text-muted-foreground mb-2">@{user.username}</p>
                )}

                {/* Quick Stats */}
                <div className="flex flex-wrap justify-center sm:justify-start gap-4 mt-4">
                  <div className="text-center">
                    <p className="text-2xl font-bold text-primary">{user.mmr ?? '—'}</p>
                    <p className="text-xs text-muted-foreground">Base MMR</p>
                  </div>
                  {user.steamid && (
                    <a
                      href={`https://www.dotabuff.com/players/${user.steamid}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-sm text-muted-foreground hover:text-primary transition-colors"
                    >
                      <ExternalLink className="h-4 w-4" />
                      Dotabuff
                    </a>
                  )}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <ScrollArea className="w-full pb-2">
          <TabsList className="inline-flex w-full min-w-max gap-1 p-1">
            <TabsTrigger value="overview" className="flex-1 min-w-[100px] min-h-11 gap-2">
              <Users className="h-4 w-4" />
              <span className="hidden sm:inline">Overview</span>
            </TabsTrigger>
            <TabsTrigger value="tournaments" className="flex-1 min-w-[100px] min-h-11 gap-2">
              <Trophy className="h-4 w-4" />
              <span className="hidden sm:inline">Tournaments</span>
            </TabsTrigger>
            <TabsTrigger value="leagues" className="flex-1 min-w-[100px] min-h-11 gap-2">
              <Award className="h-4 w-4" />
              <span className="hidden sm:inline">Leagues</span>
            </TabsTrigger>
            <TabsTrigger value="games" className="flex-1 min-w-[100px] min-h-11 gap-2">
              <Gamepad2 className="h-4 w-4" />
              <span className="hidden sm:inline">Games</span>
            </TabsTrigger>
          </TabsList>
          <ScrollBar orientation="horizontal" className="h-1.5" />
        </ScrollArea>

        <TabsContent value="overview" className="mt-4">
          <OverviewTab user={user} />
        </TabsContent>

        <TabsContent value="tournaments" className="mt-4">
          <TournamentsTab user={user} />
        </TabsContent>

        <TabsContent value="leagues" className="mt-4">
          <LeaguesTab user={user} />
        </TabsContent>

        <TabsContent value="games" className="mt-4">
          <GamesTab user={user} />
        </TabsContent>
      </Tabs>

      {/* Edit Profile Modal */}
      {isOwnProfile && (
        <EditProfileModal
          user={user}
          open={editModalOpen}
          onOpenChange={setEditModalOpen}
          onSave={() => refetch()}
        />
      )}
    </div>
  );
}

function OverviewTab({ user }: { user: UserType }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {/* Positions Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Positions</CardTitle>
        </CardHeader>
        <CardContent>
          <RolePositions user={user} />
        </CardContent>
      </Card>

      {/* Profile Details Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Profile Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Username</span>
            <span className="font-medium">{user.username}</span>
          </div>
          {user.nickname && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">Nickname</span>
              <span className="font-medium">{user.nickname}</span>
            </div>
          )}
          <div className="flex justify-between">
            <span className="text-muted-foreground">Base MMR</span>
            <span className="font-medium">{user.mmr ?? 'Not set'}</span>
          </div>
          {user.steamid && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">Steam ID</span>
              <span className="font-medium font-mono text-sm">{user.steamid}</span>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function TournamentsTab({ user }: { user: UserType }) {
  // TODO: Fetch user's tournaments from API
  return (
    <Card>
      <CardContent className="py-8">
        <div className="text-center text-muted-foreground">
          <Trophy className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>Tournament history coming soon</p>
        </div>
      </CardContent>
    </Card>
  );
}

function LeaguesTab({ user }: { user: UserType }) {
  // TODO: Fetch user's leagues from API
  return (
    <Card>
      <CardContent className="py-8">
        <div className="text-center text-muted-foreground">
          <Award className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>League standings coming soon</p>
        </div>
      </CardContent>
    </Card>
  );
}

function GamesTab({ user }: { user: UserType }) {
  // TODO: Fetch user's recent games from API
  return (
    <Card>
      <CardContent className="py-8">
        <div className="text-center text-muted-foreground">
          <Gamepad2 className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>Recent games coming soon</p>
        </div>
      </CardContent>
    </Card>
  );
}

function ProfileSkeleton() {
  return (
    <div className="container mx-auto p-4 max-w-4xl">
      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="flex flex-col sm:flex-row gap-6 items-center sm:items-start">
            <Skeleton className="w-24 h-24 sm:w-32 sm:h-32 rounded-full" />
            <div className="flex-1 space-y-3">
              <Skeleton className="h-8 w-48" />
              <Skeleton className="h-4 w-32" />
              <div className="flex gap-4">
                <Skeleton className="h-12 w-20" />
                <Skeleton className="h-12 w-20" />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
      <Skeleton className="h-12 w-full mb-4" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

export default UserProfilePage;
