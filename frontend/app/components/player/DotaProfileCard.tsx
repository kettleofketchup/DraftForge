import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil, Shield, Swords, Trophy, X } from 'lucide-react';
import { toast } from 'sonner';
import api from '~/components/api/axios';
import { Badge } from '~/components/ui/badge';
import { PrimaryButton, SecondaryButton, DestructiveButton } from '~/components/ui/buttons';
import { Card, CardContent, CardHeader } from '~/components/ui/card';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { Input } from '~/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '~/components/ui/select';
import { RolePositions } from '~/components/user/positions';

interface DotaProfile {
  id: number;
  org_user_id: number;
  rank_status: string;
  rank_medal: string;
  rank_date: string | null;
  battle_cup_tier: number | null;
  mmr: number | null;
  rank_screenshot: string | null;
  battlecup_screenshot: string | null;
  unverified_friend_id: string;
  pos_1: boolean;
  pos_2: boolean;
  pos_3: boolean;
  pos_4: boolean;
  pos_5: boolean;
}

const MEDALS = ['Herald', 'Guardian', 'Crusader', 'Archon', 'Legend', 'Ancient', 'Divine', 'Immortal'];
const STARS = ['1', '2', '3', '4', '5'];

const RANK_STATUS_LABELS: Record<string, string> = {
  active: 'Active Rank',
  previous: 'Previously Ranked',
  never: 'Never Ranked',
};

const MEDAL_COLORS: Record<string, string> = {
  Herald: 'bg-zinc-600/30 text-zinc-300 border-zinc-500/30',
  Guardian: 'bg-amber-800/30 text-amber-300 border-amber-600/30',
  Crusader: 'bg-lime-800/30 text-lime-300 border-lime-600/30',
  Archon: 'bg-sky-800/30 text-sky-300 border-sky-600/30',
  Legend: 'bg-violet-800/30 text-violet-300 border-violet-600/30',
  Ancient: 'bg-red-800/30 text-red-300 border-red-600/30',
  Divine: 'bg-cyan-800/30 text-cyan-300 border-cyan-600/30',
  Immortal: 'bg-yellow-700/30 text-yellow-200 border-yellow-500/30',
};

function getMedalColor(medal: string): string {
  const base = medal.split(' ')[0];
  return MEDAL_COLORS[base] || '';
}

interface DotaProfileCardProps {
  orgId: number;
  /** If provided, shows another user's profile (staff view). Otherwise shows current user's. */
  userPk?: number;
  isStaff?: boolean;
}

export function DotaProfileCard({ orgId, userPk, isStaff }: DotaProfileCardProps) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [showDelete, setShowDelete] = useState(false);

  const endpoint = userPk
    ? `/organizations/${orgId}/users/${userPk}/dota-profile/`
    : `/organizations/${orgId}/my-dota-profile/`;

  const updateEndpoint = userPk
    ? `/organizations/${orgId}/users/${userPk}/dota-profile/update/`
    : `/organizations/${orgId}/my-dota-profile/update/`;

  const queryKey = ['dota-profile', orgId, userPk || 'me'];

  const { data: profile, isLoading } = useQuery<DotaProfile>({
    queryKey,
    queryFn: () => api.get(endpoint).then((r) => r.data),
  });

  const updateMutation = useMutation({
    mutationFn: (data: Partial<DotaProfile>) => api.patch(updateEndpoint, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
      setEditing(false);
      toast.success('Profile updated');
    },
    onError: () => toast.error('Failed to update profile'),
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/organizations/${orgId}/users/${userPk}/dota-profile/delete/`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
      toast.success('Profile deleted');
    },
    onError: () => toast.error('Failed to delete profile'),
  });

  if (isLoading) {
    return (
      <Card className="animate-pulse">
        <CardHeader><div className="h-5 w-32 bg-base-400 rounded" /></CardHeader>
        <CardContent><div className="h-20 bg-base-400 rounded" /></CardContent>
      </Card>
    );
  }

  if (!profile) return null;

  if (editing) {
    return <DotaProfileEditForm profile={profile} onSave={(data) => updateMutation.mutate(data)} onCancel={() => setEditing(false)} saving={updateMutation.isPending} />;
  }

  const medalBase = profile.rank_medal.split(' ')[0];
  const medalStar = profile.rank_medal.split(' ')[1];

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="h-5 w-5 text-primary" />
            <h3 className="font-semibold text-sm">Dota 2 Profile</h3>
          </div>
          <div className="flex items-center gap-1">
            <SecondaryButton size="sm" onClick={() => setEditing(true)}>
              <Pencil className="h-3.5 w-3.5 mr-1" />
              Edit
            </SecondaryButton>
            {isStaff && userPk && (
              <DestructiveButton
                size="sm"
                depth={false}
                onClick={() => setShowDelete(true)}
              >
                <X className="h-3.5 w-3.5" />
              </DestructiveButton>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Rank */}
        <div className="flex items-center gap-3">
          <Badge variant="outline" className={`text-xs ${RANK_STATUS_LABELS[profile.rank_status] ? '' : 'text-muted-foreground'}`}>
            {RANK_STATUS_LABELS[profile.rank_status] || profile.rank_status}
          </Badge>
          {profile.rank_medal && (
            <Badge className={`${getMedalColor(profile.rank_medal)} text-sm font-medium`}>
              <Trophy className="h-3.5 w-3.5 mr-1" />
              {profile.rank_medal}
            </Badge>
          )}
          {profile.mmr != null && profile.mmr > 0 && (
            <span className="text-sm font-mono text-muted-foreground">{profile.mmr.toLocaleString()} MMR</span>
          )}
        </div>

        {/* Battle Cup */}
        {profile.battle_cup_tier && (
          <div className="flex items-center gap-2">
            <Swords className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">Battle Cup Tier {profile.battle_cup_tier}</span>
          </div>
        )}

        {/* Positions */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Positions:</span>
          <RolePositions
            user={{
              positions: {
                carry: profile.pos_1 ? 1 : 0,
                mid: profile.pos_2 ? 1 : 0,
                offlane: profile.pos_3 ? 1 : 0,
                soft_support: profile.pos_4 ? 1 : 0,
                hard_support: profile.pos_5 ? 1 : 0,
              },
            }}
            compact
          />
        </div>

        {/* Friend ID */}
        {profile.unverified_friend_id && (
          <div className="text-xs text-muted-foreground">
            Friend ID: <code className="bg-base-400 px-1 rounded">{profile.unverified_friend_id}</code>
          </div>
        )}

        {/* Screenshots */}
        {(profile.rank_screenshot || profile.battlecup_screenshot) && (
          <div className="flex gap-2">
            {profile.rank_screenshot && (
              <a href={profile.rank_screenshot} target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline">
                Rank Screenshot
              </a>
            )}
            {profile.battlecup_screenshot && (
              <a href={profile.battlecup_screenshot} target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline">
                Battle Cup Screenshot
              </a>
            )}
          </div>
        )}
      </CardContent>
      <ConfirmDialog
        open={showDelete}
        onOpenChange={setShowDelete}
        title="Delete Dota Profile?"
        description="This will permanently delete this player's Dota profile. This cannot be undone."
        confirmLabel="Delete Profile"
        variant="destructive"
        isLoading={deleteMutation.isPending}
        onConfirm={async () => {
          try {
            await deleteMutation.mutateAsync();
          } catch {
            // toast handled by mutation onError
          }
        }}
        contentTestId="delete-dota-profile-dialog"
        confirmTestId="delete-dota-profile-confirm"
        cancelTestId="delete-dota-profile-cancel"
      />
    </Card>
  );
}

/** Inline edit form */
function DotaProfileEditForm({
  profile,
  onSave,
  onCancel,
  saving,
}: {
  profile: DotaProfile;
  onSave: (data: Partial<DotaProfile>) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [rankStatus, setRankStatus] = useState(profile.rank_status);
  const medalParts = profile.rank_medal.split(' ');
  const [medal, setMedal] = useState(medalParts[0] || '');
  const [star, setStar] = useState(medalParts[1] || '1');
  const [mmr, setMmr] = useState(profile.mmr?.toString() || '');
  const [battleCupTier, setBattleCupTier] = useState(profile.battle_cup_tier?.toString() || '');
  const [friendId, setFriendId] = useState(profile.unverified_friend_id || '');
  const [pos1, setPos1] = useState(profile.pos_1);
  const [pos2, setPos2] = useState(profile.pos_2);
  const [pos3, setPos3] = useState(profile.pos_3);
  const [pos4, setPos4] = useState(profile.pos_4);
  const [pos5, setPos5] = useState(profile.pos_5);

  const handleSave = () => {
    const rankMedal = medal ? (medal === 'Immortal' ? 'Immortal' : `${medal} ${star}`) : '';
    onSave({
      rank_status: rankStatus,
      rank_medal: rankMedal,
      mmr: mmr ? parseInt(mmr) : null,
      battle_cup_tier: battleCupTier ? parseInt(battleCupTier) : null,
      unverified_friend_id: friendId,
      pos_1: pos1,
      pos_2: pos2,
      pos_3: pos3,
      pos_4: pos4,
      pos_5: pos5,
    });
  };

  const positions = [
    { key: 'pos_1', label: 'Carry', value: pos1, set: setPos1 },
    { key: 'pos_2', label: 'Mid', value: pos2, set: setPos2 },
    { key: 'pos_3', label: 'Offlane', value: pos3, set: setPos3 },
    { key: 'pos_4', label: 'Soft Sup', value: pos4, set: setPos4 },
    { key: 'pos_5', label: 'Hard Sup', value: pos5, set: setPos5 },
  ];

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="h-5 w-5 text-primary" />
            <h3 className="font-semibold text-sm">Edit Dota 2 Profile</h3>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Rank Status */}
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Rank Status</label>
          <Select value={rankStatus} onValueChange={setRankStatus}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="active">Active Rank</SelectItem>
              <SelectItem value="previous">Previously Ranked</SelectItem>
              <SelectItem value="never">Never Ranked</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Medal + Star (active/previous) */}
        {rankStatus !== 'never' && (
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Medal</label>
              <Select value={medal} onValueChange={setMedal}>
                <SelectTrigger>
                  <SelectValue placeholder="Select medal" />
                </SelectTrigger>
                <SelectContent>
                  {MEDALS.map((m) => (
                    <SelectItem key={m} value={m}>{m}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {medal && medal !== 'Immortal' && (
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Star</label>
                <Select value={star} onValueChange={setStar}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {STARS.map((s) => (
                      <SelectItem key={s} value={s}>Star {s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
        )}

        {/* MMR */}
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">MMR (optional)</label>
          <Input
            type="number"
            placeholder="e.g. 4500"
            value={mmr}
            onChange={(e) => setMmr(e.target.value)}
          />
        </div>

        {/* Battle Cup Tier (never ranked) */}
        {rankStatus === 'never' && (
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">Battle Cup Tier</label>
            <Input
              type="number"
              min="1"
              max="8"
              placeholder="e.g. 5"
              value={battleCupTier}
              onChange={(e) => setBattleCupTier(e.target.value)}
            />
          </div>
        )}

        {/* Friend ID */}
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Dota 2 Friend ID</label>
          <Input
            placeholder="e.g. 123456789"
            value={friendId}
            onChange={(e) => setFriendId(e.target.value)}
          />
        </div>

        {/* Positions */}
        <div>
          <label className="text-xs text-muted-foreground mb-1.5 block">Preferred Positions</label>
          <div className="flex flex-wrap gap-2">
            {positions.map((p) => (
              <button
                key={p.key}
                type="button"
                onClick={() => p.set(!p.value)}
                className={`px-3 py-1.5 text-xs rounded-md border transition-colors cursor-pointer ${
                  p.value
                    ? 'bg-primary/20 text-primary border-primary/30 font-medium'
                    : 'bg-muted/30 text-muted-foreground border-border hover:bg-muted/50'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 pt-2">
          <PrimaryButton size="sm" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving...' : 'Save'}
          </PrimaryButton>
          <SecondaryButton size="sm" onClick={onCancel}>
            Cancel
          </SecondaryButton>
        </div>
      </CardContent>
    </Card>
  );
}
