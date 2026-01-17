# Captain & Player Popovers Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add captain popovers showing team roster during draft order, and player popovers/modals with a humorous "Under Construction" extended profile that tracks tango purchases.

**Architecture:** Backend Django model for Joke (tangoes), REST API endpoints, frontend React components using Radix Popover/Dialog primitives, React Query for state management.

**Tech Stack:** Django, Django REST Framework, React, TypeScript, Radix UI (Popover/Dialog), React Query, Zod, Tailwind CSS, Axios

---

## Task 0: Frontend - Install Progress Component

**Files:**
- Create: `frontend/app/components/ui/progress.tsx`

**Step 1: Install Progress component from shadcn/ui**

Run from frontend directory:
```bash
cd frontend && npx shadcn@latest add progress
```

**Step 2: Verify installation**

Run: `ls frontend/app/components/ui/progress.tsx`
Expected: File exists

**Step 3: Commit**

```bash
git add frontend/app/components/ui/progress.tsx
git commit -m "feat: add shadcn Progress component"
```

---

## Task 1: Backend - Create Joke Model

**Files:**
- Modify: `backend/app/models.py`

**Step 1: Add Joke model to models.py**

Add at the end of the file (after the last model):

```python
class Joke(models.Model):
    """Tracks joke-related data per user (tangoes purchased, etc.)."""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='joke'
    )
    tangoes_purchased = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Joke"
        verbose_name_plural = "Jokes"

    def __str__(self):
        return f"{self.user.username} - {self.tangoes_purchased} tangoes"
```

**Step 2: Run makemigrations**

Run: `source .venv/bin/activate && inv test.run --cmd 'python manage.py makemigrations app'`
Expected: Migration file created

**Step 3: Run migrate for all environments**

Run: `source .venv/bin/activate && inv db.migrate.all`
Expected: Migrations applied successfully

**Step 4: Commit**

```bash
git add backend/app/models.py backend/app/migrations/
git commit -m "feat: add Joke model for tangoes tracking"
```

---

## Task 2: Backend - Create Joke Serializer

**Files:**
- Modify: `backend/app/serializers.py`

**Step 1: Add JokeSerializer**

Add import at top with other model imports:

```python
from .models import (
    CustomUser,
    Draft,
    DraftRound,
    Game,
    Joke,  # Add this
    PositionsModel,
    Team,
    Tournament,
)
```

Add serializer at end of file:

```python
class JokeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Joke
        fields = ['tangoes_purchased']
        read_only_fields = ['tangoes_purchased']
```

**Step 2: Commit**

```bash
git add backend/app/serializers.py
git commit -m "feat: add JokeSerializer"
```

---

## Task 3: Backend - Create Joke API Views

**Files:**
- Create: `backend/app/views_joke.py`

**Step 1: Create views_joke.py**

```python
"""Views for joke-related endpoints (tangoes, etc.)."""
import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Joke
from .serializers import JokeSerializer

log = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_tangoes(request):
    """Get current user's tango count."""
    joke, created = Joke.objects.get_or_create(user=request.user)
    serializer = JokeSerializer(joke)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def buy_tango(request):
    """Increment user's tango count by 1."""
    joke, created = Joke.objects.get_or_create(user=request.user)
    joke.tangoes_purchased += 1
    joke.save()

    return Response({
        'tangoes_purchased': joke.tangoes_purchased,
        'message': 'You bought a tango! 🌿'
    }, status=status.HTTP_200_OK)
```

**Step 2: Commit**

```bash
git add backend/app/views_joke.py
git commit -m "feat: add joke API views for tangoes"
```

---

## Task 4: Backend - Register Joke URL Routes

**Files:**
- Modify: `backend/backend/urls.py`

**Step 1: Add imports and routes**

Add import after other app imports:

```python
from app.views_joke import buy_tango, get_tangoes
```

Add URL patterns in the urlpatterns list (after the `api/profile_update` line):

```python
    path("api/jokes/tangoes/", get_tangoes, name="get-tangoes"),
    path("api/jokes/tangoes/buy/", buy_tango, name="buy-tango"),
```

**Step 2: Commit**

```bash
git add backend/backend/urls.py
git commit -m "feat: register joke API routes"
```

---

## Task 5: Backend - Write Joke API Tests

**Files:**
- Create: `backend/app/tests/test_joke.py`

**Step 1: Create test file**

```python
"""Tests for joke API endpoints."""
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from app.models import CustomUser, Joke


class JokeAPITest(TestCase):
    """Test joke API endpoints."""

    def setUp(self):
        """Create test user."""
        self.user = CustomUser.objects.create_user(
            username="testuser",
            password="test123",
        )
        self.client = APIClient()

    def test_get_tangoes_requires_auth(self):
        """GET /api/jokes/tangoes/ requires authentication."""
        response = self.client.get("/api/jokes/tangoes/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_tangoes_creates_joke_if_not_exists(self):
        """GET /api/jokes/tangoes/ creates Joke record if none exists."""
        self.client.force_authenticate(user=self.user)

        self.assertFalse(Joke.objects.filter(user=self.user).exists())

        response = self.client.get("/api/jokes/tangoes/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['tangoes_purchased'], 0)
        self.assertTrue(Joke.objects.filter(user=self.user).exists())

    def test_get_tangoes_returns_existing_count(self):
        """GET /api/jokes/tangoes/ returns existing tango count."""
        self.client.force_authenticate(user=self.user)
        Joke.objects.create(user=self.user, tangoes_purchased=42)

        response = self.client.get("/api/jokes/tangoes/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['tangoes_purchased'], 42)

    def test_buy_tango_requires_auth(self):
        """POST /api/jokes/tangoes/buy/ requires authentication."""
        response = self.client.post("/api/jokes/tangoes/buy/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_buy_tango_increments_count(self):
        """POST /api/jokes/tangoes/buy/ increments tango count."""
        self.client.force_authenticate(user=self.user)
        Joke.objects.create(user=self.user, tangoes_purchased=10)

        response = self.client.post("/api/jokes/tangoes/buy/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['tangoes_purchased'], 11)
        self.assertIn('message', response.data)

    def test_buy_tango_creates_joke_if_not_exists(self):
        """POST /api/jokes/tangoes/buy/ creates Joke if none exists."""
        self.client.force_authenticate(user=self.user)

        response = self.client.post("/api/jokes/tangoes/buy/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['tangoes_purchased'], 1)
```

**Step 2: Run tests to verify they pass**

Run: `source .venv/bin/activate && inv test.run --cmd 'python manage.py test app.tests.test_joke -v 2'`
Expected: All tests pass

**Step 3: Commit**

```bash
git add backend/app/tests/test_joke.py
git commit -m "test: add joke API tests"
```

---

## Task 6: Frontend - Create useTangoes Hook

**Files:**
- Create: `frontend/app/hooks/useTangoes.ts`

**Step 1: Create hook file**

Uses axios for CSRF token handling and toast for error feedback:

```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { z } from 'zod';
import api from '~/components/api/axios';

const TangoesResponseSchema = z.object({
  tangoes_purchased: z.number(),
});

const BuyTangoResponseSchema = z.object({
  tangoes_purchased: z.number(),
  message: z.string(),
});

interface UseTangoesReturn {
  tangoes: number;
  isLoading: boolean;
  buyTango: () => void;
  isBuying: boolean;
  error: Error | null;
}

async function fetchTangoes(): Promise<number> {
  const response = await api.get('/jokes/tangoes/');
  const parsed = TangoesResponseSchema.parse(response.data);
  return parsed.tangoes_purchased;
}

async function buyTangoRequest(): Promise<{ tangoes: number; message: string }> {
  const response = await api.post('/jokes/tangoes/buy/');
  const parsed = BuyTangoResponseSchema.parse(response.data);
  return { tangoes: parsed.tangoes_purchased, message: parsed.message };
}

export function useTangoes(enabled: boolean = true): UseTangoesReturn {
  const queryClient = useQueryClient();

  const tangoesQuery = useQuery({
    queryKey: ['tangoes'],
    queryFn: fetchTangoes,
    enabled,
  });

  const buyTangoMutation = useMutation({
    mutationFn: buyTangoRequest,
    onSuccess: (data) => {
      queryClient.setQueryData(['tangoes'], data.tangoes);
      toast.success(data.message);
    },
    onError: (error: any) => {
      const message = error?.response?.data?.detail || 'Failed to buy tango';
      toast.error(message);
    },
  });

  return {
    tangoes: tangoesQuery.data ?? 0,
    isLoading: tangoesQuery.isLoading,
    buyTango: () => buyTangoMutation.mutate(),
    isBuying: buyTangoMutation.isPending,
    error: tangoesQuery.error,
  };
}
```

**Step 2: Commit**

```bash
git add frontend/app/hooks/useTangoes.ts
git commit -m "feat: add useTangoes hook with axios and toast notifications"
```

---

## Task 7: Frontend - Create PlayerUnderConstruction Component

**Files:**
- Create: `frontend/app/components/player/PlayerUnderConstruction.tsx`

**Step 1: Create the component**

Includes useMemo for computed values and accessibility attributes:

```typescript
import { memo, useMemo } from 'react';
import { Construction } from 'lucide-react';
import { Button } from '~/components/ui/button';
import { Progress } from '~/components/ui/progress';
import { useTangoes } from '~/hooks/useTangoes';
import { useUserStore } from '~/store/userStore';

const GAMES_TO_THROW = 10;
const GAMES_THROWN = 2; // Always 2/10 - it's a joke
const TANGOES_REQUIRED = 46326;

interface PlayerUnderConstructionProps {
  playerName: string;
}

export const PlayerUnderConstruction: React.FC<PlayerUnderConstructionProps> = memo(({
  playerName,
}) => {
  const currentUser = useUserStore((state) => state.currentUser);
  const isLoggedIn = !!currentUser?.pk;
  const { tangoes, buyTango, isBuying, isLoading } = useTangoes(isLoggedIn);

  const gamesProgress = useMemo(
    () => (GAMES_THROWN / GAMES_TO_THROW) * 100,
    []
  );

  const tangoesProgress = useMemo(
    () => Math.min((tangoes / TANGOES_REQUIRED) * 100, 100),
    [tangoes]
  );

  return (
    <div className="border border-dashed border-yellow-500/50 rounded-lg p-4 bg-yellow-950/10">
      <div className="flex items-center justify-center gap-2 mb-4">
        <Construction className="h-5 w-5 text-yellow-500" aria-hidden="true" />
        <h3 className="text-lg font-semibold text-yellow-500">
          EXTENDED PROFILE UNDER CONSTRUCTION
        </h3>
        <Construction className="h-5 w-5 text-yellow-500" aria-hidden="true" />
      </div>

      <p className="text-center text-muted-foreground mb-4">
        To unlock {playerName}'s extended profile:
      </p>

      {/* Option A: Throw games */}
      <div className="border border-muted rounded-lg p-3 mb-3">
        <p className="font-medium mb-2">
          Option A: Throw {GAMES_TO_THROW} of {playerName}'s games
        </p>
        <div className="flex items-center gap-2">
          <Progress
            value={gamesProgress}
            className="flex-1"
            aria-label={`${GAMES_THROWN} of ${GAMES_TO_THROW} games thrown`}
          />
          <span className="text-sm text-muted-foreground whitespace-nowrap">
            {GAMES_THROWN}/{GAMES_TO_THROW} games thrown
          </span>
        </div>
      </div>

      <p className="text-center text-muted-foreground my-2">— OR —</p>

      {/* Option B: Buy tangoes */}
      <div className="border border-muted rounded-lg p-3">
        <p className="font-medium mb-2">
          Option B: Purchase {TANGOES_REQUIRED.toLocaleString()} tangoes
        </p>
        <div className="flex items-center gap-2 mb-2">
          <span className="text-lg" aria-hidden="true">🌿</span>
          <Progress
            value={tangoesProgress}
            className="flex-1"
            aria-label={`${tangoes} of ${TANGOES_REQUIRED} tangoes purchased`}
          />
          <span className="text-sm text-muted-foreground whitespace-nowrap">
            {tangoes.toLocaleString()} / {TANGOES_REQUIRED.toLocaleString()}
          </span>
        </div>
        {isLoggedIn ? (
          <Button
            variant="outline"
            size="sm"
            onClick={buyTango}
            disabled={isBuying || isLoading}
            className="w-full"
            aria-busy={isBuying}
          >
            🌿 {isBuying ? 'Buying...' : 'Buy Tango'}
          </Button>
        ) : (
          <p className="text-sm text-muted-foreground text-center">
            Log in to purchase tangoes
          </p>
        )}
      </div>
    </div>
  );
});

PlayerUnderConstruction.displayName = 'PlayerUnderConstruction';
```

**Step 2: Commit**

```bash
git add frontend/app/components/player/PlayerUnderConstruction.tsx
git commit -m "feat: add PlayerUnderConstruction component with tango jokes"
```

---

## Task 8: Frontend - Create PlayerModal Component

**Files:**
- Create: `frontend/app/components/player/PlayerModal.tsx`

**Step 1: Create the component**

```typescript
import { Badge } from '~/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { RolePositions } from '~/components/user/positions';
import type { UserType } from '~/components/user/types';
import { User } from '~/components/user/user';
import UserEditModal from '~/components/user/userCard/editModal';
import { AvatarUrl } from '~/index';
import { useUserStore } from '~/store/userStore';
import { PlayerUnderConstruction } from './PlayerUnderConstruction';

interface PlayerModalProps {
  player: UserType;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const PlayerModal: React.FC<PlayerModalProps> = ({
  player,
  open,
  onOpenChange,
}) => {
  const currentUser = useUserStore((state) => state.currentUser);
  const canEdit = currentUser?.is_staff || currentUser?.is_superuser;
  const playerName = player.nickname || player.username || 'Unknown';

  const goToDotabuff = () => {
    if (!player.steamid) return '#';
    return `https://www.dotabuff.com/players/${encodeURIComponent(String(player.steamid))}`;
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Player Profile</DialogTitle>
        </DialogHeader>

        {/* User Card Section */}
        <div className="space-y-4">
          {/* Header with avatar and name */}
          <div className="flex items-center gap-4">
            <img
              src={AvatarUrl(player)}
              alt={`${playerName}'s avatar`}
              className="w-16 h-16 rounded-full border border-primary"
            />
            <div className="flex-1">
              <h2 className="text-xl font-semibold">{playerName}</h2>
              <div className="flex gap-2 mt-1">
                {player.is_staff && (
                  <Badge className="bg-blue-700 text-white">Staff</Badge>
                )}
                {player.is_superuser && (
                  <Badge className="bg-red-700 text-white">Admin</Badge>
                )}
              </div>
            </div>
            {canEdit && player.pk && <UserEditModal user={new User(player)} />}
          </div>

          {/* Player info */}
          <div className="space-y-2 text-sm">
            {player.username && (
              <div>
                <span className="font-semibold">Username:</span> {player.username}
              </div>
            )}
            {player.nickname && (
              <div>
                <span className="font-semibold">Nickname:</span> {player.nickname}
              </div>
            )}
            {player.mmr && (
              <div>
                <span className="font-semibold">MMR:</span> {player.mmr}
              </div>
            )}
            <RolePositions user={player} />
            {player.steamid && (
              <div>
                <span className="font-semibold">Steam ID:</span> {player.steamid}
              </div>
            )}
          </div>

          {/* Dotabuff link */}
          {player.steamid && (
            <a
              className="flex items-center justify-center btn btn-sm btn-outline w-full"
              href={goToDotabuff()}
              target="_blank"
              rel="noopener noreferrer"
            >
              <img
                src="https://cdn.brandfetch.io/idKrze_WBi/w/96/h/96/theme/dark/logo.png?c=1dxbfHSJFAPEGdCLU4o5B"
                alt="Dotabuff Logo"
                className="w-4 h-4 mr-2"
              />
              Dotabuff Profile
            </a>
          )}

          {/* Extended Profile (Under Construction) */}
          <PlayerUnderConstruction playerName={playerName} />
        </div>
      </DialogContent>
    </Dialog>
  );
};
```

**Step 2: Commit**

```bash
git add frontend/app/components/player/PlayerModal.tsx
git commit -m "feat: add PlayerModal component with full profile view"
```

---

## Task 9: Frontend - Create PlayerPopover Component

**Files:**
- Create: `frontend/app/components/player/PlayerPopover.tsx`

**Step 1: Create the component**

Includes useCallback for event handlers and keyboard accessibility:

```typescript
import { useCallback, useState } from 'react';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import { RolePositions } from '~/components/user/positions';
import type { UserType } from '~/components/user/types';
import { AvatarUrl } from '~/index';
import { PlayerModal } from './PlayerModal';

interface PlayerPopoverProps {
  player: UserType;
  children: React.ReactNode;
}

export const PlayerPopover: React.FC<PlayerPopoverProps> = ({
  player,
  children,
}) => {
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const playerName = player.nickname || player.username || 'Unknown';

  const handleClick = useCallback(() => {
    setPopoverOpen(false);
    setModalOpen(true);
  }, []);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleClick();
    }
  }, [handleClick]);

  return (
    <>
      <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
        <PopoverTrigger asChild onClick={handleClick}>
          <span
            className="cursor-pointer"
            role="button"
            tabIndex={0}
            aria-label={`View profile for ${playerName}`}
            onKeyDown={handleKeyDown}
          >
            {children}
          </span>
        </PopoverTrigger>
        <PopoverContent
          className="w-56 p-3"
          onOpenAutoFocus={(e) => e.preventDefault()}
        >
          <div className="space-y-2">
            {/* Header with avatar and name */}
            <div className="flex items-center gap-3">
              <img
                src={AvatarUrl(player)}
                alt={`${playerName}'s avatar`}
                className="w-12 h-12 rounded-full"
              />
              <div>
                <p className="font-medium">{playerName}</p>
                {player.mmr && (
                  <p className="text-sm text-muted-foreground">
                    MMR: {player.mmr}
                  </p>
                )}
              </div>
            </div>

            {/* Positions */}
            <RolePositions user={player} />

            {/* Click hint */}
            <p className="text-xs text-muted-foreground text-center pt-1">
              Click for full profile
            </p>
          </div>
        </PopoverContent>
      </Popover>

      <PlayerModal
        player={player}
        open={modalOpen}
        onOpenChange={setModalOpen}
      />
    </>
  );
};
```

**Step 2: Commit**

```bash
git add frontend/app/components/player/PlayerPopover.tsx
git commit -m "feat: add PlayerPopover component with keyboard accessibility"
```

---

## Task 10: Frontend - Create Player Component Index

**Files:**
- Create: `frontend/app/components/player/index.ts`

**Step 1: Create index file**

```typescript
export { PlayerModal } from './PlayerModal';
export { PlayerPopover } from './PlayerPopover';
export { PlayerUnderConstruction } from './PlayerUnderConstruction';
```

**Step 2: Commit**

```bash
git add frontend/app/components/player/index.ts
git commit -m "feat: add player component exports"
```

---

## Task 11: Frontend - Create CaptainPopover Component

**Files:**
- Create: `frontend/app/components/captain/CaptainPopover.tsx`

**Step 1: Create the component**

Uses correct type imports and useMemo for computed values:

```typescript
import { useMemo, useState } from 'react';
import type { TeamType } from '~/components/tournament/types';
import type { UserType } from '~/components/user/types';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import { TeamTable } from '~/components/team/teamTable/teamTable';

interface CaptainPopoverProps {
  captain: UserType;
  team: TeamType;
  children: React.ReactNode;
}

export const CaptainPopover: React.FC<CaptainPopoverProps> = ({
  captain,
  team,
  children,
}) => {
  const [open, setOpen] = useState(false);

  const avgMMR = useMemo(() => {
    if (!team.members || team.members.length === 0) return 0;
    const total = team.members.reduce((sum, m) => sum + (m.mmr || 0), 0);
    return Math.round(total / team.members.length);
  }, [team.members]);

  const teamName = team.name || `${captain.nickname || captain.username}'s Team`;
  const hasMembers = team.members && team.members.length > 0;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <span
          className="cursor-pointer"
          role="button"
          tabIndex={0}
          aria-label={`View ${teamName} roster`}
        >
          {children}
        </span>
      </PopoverTrigger>
      <PopoverContent
        className="w-80 p-0"
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-3 border-b">
          <span className="font-medium">{teamName}</span>
          {hasMembers && (
            <span className="text-sm text-muted-foreground">
              Avg: {avgMMR.toLocaleString()} MMR
            </span>
          )}
        </div>

        {/* Team Table or Empty State */}
        <div className="max-h-64 overflow-y-auto">
          {hasMembers ? (
            <TeamTable team={team} />
          ) : (
            <div className="p-4 text-center text-muted-foreground">
              No players drafted yet
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
};
```

**Step 2: Create index file**

Create `frontend/app/components/captain/index.ts`:

```typescript
export { CaptainPopover } from './CaptainPopover';
```

**Step 3: Commit**

```bash
git add frontend/app/components/captain/
git commit -m "feat: add CaptainPopover component showing team roster"
```

---

## Task 12: Frontend - Integrate CaptainPopover in ShufflePickOrder

**Files:**
- Modify: `frontend/app/components/draft/shuffle/ShufflePickOrder.tsx`

**Step 1: Add import**

Add after existing imports:

```typescript
import { CaptainPopover } from '~/components/captain';
```

**Step 2: Wrap captain avatar and name with CaptainPopover (with null safety)**

Find the section inside the Card that renders captain avatar and name (around lines 125-137).

Replace:

```typescript
            <div className="flex flex-col gap-1 items-center">
              {/* Captain avatar */}
              <img
                src={AvatarUrl(status.team.captain)}
                alt={status.team.captain?.username || 'Captain'}
                className="w-10 h-10 rounded-full"
              />

              {/* Captain name */}
              <span className="font-medium text-sm truncate text-center">
                {status.team.captain?.nickname || status.team.captain?.username || 'Unknown'}
              </span>
```

With (includes null safety check):

```typescript
            <div className="flex flex-col gap-1 items-center">
              {status.team.captain ? (
                <>
                  <CaptainPopover captain={status.team.captain} team={status.team}>
                    {/* Captain avatar */}
                    <img
                      src={AvatarUrl(status.team.captain)}
                      alt={status.team.captain?.username || 'Captain'}
                      className="w-10 h-10 rounded-full hover:ring-2 hover:ring-primary transition-all"
                    />
                  </CaptainPopover>

                  {/* Captain name */}
                  <CaptainPopover captain={status.team.captain} team={status.team}>
                    <span className="font-medium text-sm truncate text-center hover:text-primary transition-colors">
                      {status.team.captain?.nickname || status.team.captain?.username || 'Unknown'}
                    </span>
                  </CaptainPopover>
                </>
              ) : (
                <>
                  <div className="w-10 h-10 rounded-full bg-muted" />
                  <span className="font-medium text-sm truncate text-center text-muted-foreground">
                    No Captain
                  </span>
                </>
              )}
```

**Step 3: Commit**

```bash
git add frontend/app/components/draft/shuffle/ShufflePickOrder.tsx
git commit -m "feat: integrate CaptainPopover in ShufflePickOrder"
```

---

## Task 13: Frontend - Integrate PlayerPopover in TeamTable

**Files:**
- Modify: `frontend/app/components/team/teamTable/teamTable.tsx`

**Step 1: Add import**

Add after existing imports:

```typescript
import { PlayerPopover } from '~/components/player';
```

**Step 2: Wrap player avatar and name with PlayerPopover**

Find the TableCell that renders member avatar and name (around lines 62-83).

Replace:

```typescript
            <TableCell>
              <div className="flex items-center gap-2">
                <span className="avatar w-8 h-8">
                  <img
                    src={AvatarUrl(user)}
                    alt={user.username}
                    className="rounded-full"
                  />
                </span>
                <span className="hidden 3xl:inline">
                  {user.nickname || user.username}
                </span>
                <span
                  className="inline 3xl:hidden"
                  title={user.nickname || user.username}
                >
                  {(user.nickname || user.username).length > 10
                    ? `${(user.nickname || user.username).substring(0, 12)}...`
                    : user.nickname || user.username}
                </span>
              </div>
            </TableCell>
```

With:

```typescript
            <TableCell>
              <PlayerPopover player={user}>
                <div className="flex items-center gap-2 hover:text-primary transition-colors">
                  <span className="avatar w-8 h-8">
                    <img
                      src={AvatarUrl(user)}
                      alt={user.username}
                      className="rounded-full hover:ring-2 hover:ring-primary transition-all"
                    />
                  </span>
                  <span className="hidden 3xl:inline">
                    {user.nickname || user.username}
                  </span>
                  <span
                    className="inline 3xl:hidden"
                    title={user.nickname || user.username}
                  >
                    {(user.nickname || user.username).length > 10
                      ? `${(user.nickname || user.username).substring(0, 12)}...`
                      : user.nickname || user.username}
                  </span>
                </div>
              </PlayerPopover>
            </TableCell>
```

**Step 3: Commit**

```bash
git add frontend/app/components/team/teamTable/teamTable.tsx
git commit -m "feat: integrate PlayerPopover in TeamTable"
```

---

## Task 14: Frontend - Integrate PlayerPopover in CaptainTable

**Files:**
- Modify: `frontend/app/components/tournament/captains/captainTable.tsx`

**Step 1: Add import**

Add after existing imports:

```typescript
import { PlayerPopover } from '~/components/player';
```

**Step 2: Wrap player avatar and name with PlayerPopover**

Find the TableCell that renders user avatar and name (look for the pattern with avatar w-8 h-8).

Wrap the content inside the TableCell containing the avatar/name with:

```typescript
<PlayerPopover player={user}>
  {/* existing avatar and name content */}
</PlayerPopover>
```

Add hover styles to the container div: `hover:text-primary transition-colors`
Add hover styles to the img: `hover:ring-2 hover:ring-primary transition-all`

**Step 3: Commit**

```bash
git add frontend/app/components/tournament/captains/captainTable.tsx
git commit -m "feat: integrate PlayerPopover in CaptainTable"
```

---

## Task 15: Frontend - Integrate PlayerPopover in DraftTable

**Files:**
- Modify: `frontend/app/components/draft/roundView/draftTable.tsx`

**Step 1: Add import**

Add after existing imports:

```typescript
import { PlayerPopover } from '~/components/player';
```

**Step 2: Wrap player avatar and name with PlayerPopover**

Find the TableCell that renders user avatar and name in the draft pool table.

Wrap the content inside the TableCell containing the avatar/name with:

```typescript
<PlayerPopover player={user}>
  {/* existing avatar and name content */}
</PlayerPopover>
```

Add hover styles to the container div: `hover:text-primary transition-colors`
Add hover styles to the img: `hover:ring-2 hover:ring-primary transition-all`

**Step 3: Commit**

```bash
git add frontend/app/components/draft/roundView/draftTable.tsx
git commit -m "feat: integrate PlayerPopover in DraftTable"
```

---

## Task 16: Test Full Integration

**Step 1: Start test environment**

Run: `source .venv/bin/activate && inv test.up`

**Step 2: Run backend tests**

Run: `source .venv/bin/activate && inv test.run --cmd 'python manage.py test app.tests -v 2'`
Expected: All tests pass

**Step 3: Test manually in browser**

1. Navigate to a tournament draft in shuffle mode
2. Hover over captain avatars in ShufflePickOrder - verify team popover appears
3. Click on a player in any TeamTable - verify popover then modal appears
4. In modal, verify "Under Construction" section displays
5. Click "Buy Tango" button (if logged in) - verify count increments and toast appears
6. Refresh page - verify tango count persists
7. Test keyboard navigation (Tab to player, Enter to open modal)
8. Test PlayerPopover in CaptainTable
9. Test PlayerPopover in DraftTable (draft pool)

**Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "fix: address integration issues"
```

---

## Task 17: Final Cleanup and Documentation

**Step 1: Update design doc status**

Edit `docs/plans/2026-01-16-captain-player-popovers-design.md` and change:

```markdown
**Status:** Draft
```

To:

```markdown
**Status:** Implemented
```

**Step 2: Commit**

```bash
git add docs/plans/2026-01-16-captain-player-popovers-design.md
git commit -m "docs: mark captain/player popovers design as implemented"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 0 | Install Progress component | `frontend/app/components/ui/progress.tsx` |
| 1 | Create Joke model | `backend/app/models.py` |
| 2 | Create JokeSerializer | `backend/app/serializers.py` |
| 3 | Create Joke API views | `backend/app/views_joke.py` |
| 4 | Register Joke URL routes | `backend/backend/urls.py` |
| 5 | Write Joke API tests | `backend/app/tests/test_joke.py` |
| 6 | Create useTangoes hook (axios + toast) | `frontend/app/hooks/useTangoes.ts` |
| 7 | Create PlayerUnderConstruction | `frontend/app/components/player/PlayerUnderConstruction.tsx` |
| 8 | Create PlayerModal | `frontend/app/components/player/PlayerModal.tsx` |
| 9 | Create PlayerPopover (keyboard a11y) | `frontend/app/components/player/PlayerPopover.tsx` |
| 10 | Create player index | `frontend/app/components/player/index.ts` |
| 11 | Create CaptainPopover (useMemo) | `frontend/app/components/captain/CaptainPopover.tsx` |
| 12 | Integrate CaptainPopover (null safe) | `frontend/app/components/draft/shuffle/ShufflePickOrder.tsx` |
| 13 | Integrate PlayerPopover in TeamTable | `frontend/app/components/team/teamTable/teamTable.tsx` |
| 14 | Integrate PlayerPopover in CaptainTable | `frontend/app/components/tournament/captains/captainTable.tsx` |
| 15 | Integrate PlayerPopover in DraftTable | `frontend/app/components/draft/roundView/draftTable.tsx` |
| 16 | Test full integration | Manual testing |
| 17 | Final cleanup | `docs/plans/...` |

---

## Review Changes Applied

Based on 3 independent reviews, the following improvements were made:

| Issue | Fix Applied |
|-------|-------------|
| Missing Progress component | Added Task 0 to install shadcn Progress |
| CSRF token missing for POST | Task 6 now uses axios instead of fetch |
| No error toast feedback | Task 6 includes toast.success/error |
| Missing CaptainTable integration | Added Task 14 |
| Missing DraftTable integration | Added Task 15 |
| Null safety for captain prop | Task 12 includes null check |
| Wrong type imports | Task 11 uses correct import paths |
| Missing useMemo | Tasks 7, 11 include useMemo for computed values |
| Missing useCallback | Task 9 includes useCallback for handlers |
| Missing keyboard accessibility | Tasks 9, 11 include role, tabIndex, onKeyDown |
| Missing aria labels | Tasks 7, 8, 9, 11 include aria attributes |
| Missing memo | Task 7 wraps component in memo() |
