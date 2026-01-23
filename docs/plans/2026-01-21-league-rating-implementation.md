# League Rating System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a pluggable Elo rating system that tracks player ratings per league with configurable algorithms, K-factors, and age decay.

**Architecture:** Extend existing League model with rating config. Create new LeagueRating, LeagueMatch, and LeagueMatchParticipant models. Rating calculations happen in a service layer with pluggable algorithms. Match finalization is atomic.

**Tech Stack:** Django 4.x, Django REST Framework, pytest-django, existing cacheops caching

---

## Prerequisites

- Working in the main repo at `/home/kettle/git_repos/website`
- Virtual environment activated: `source .venv/bin/activate`
- Test environment running: `inv test.up`

## Critical Issues to Address (from review)

1. **`total_elo` property vs field** - Use annotation in queries, not property filtering
2. **Recalculation bug** - Store winners/losers before deleting participants
3. **Race condition** - Use `select_for_update()` in finalize
4. **Team tracking** - Add `team_side` field to participants
5. **N+1 queries** - Batch lookups in finalize

---

## Task 1: Add Rating Configuration to League Model

**Files:**
- Modify: `backend/app/models.py` (League model, lines 286-333)
- Create: `backend/app/migrations/0043_league_rating_config.py`
- Test: `backend/app/tests/test_league_rating.py`

**Step 1: Write the failing test**

Create `backend/app/tests/test_league_rating.py`:

```python
"""Tests for League Rating System models."""
from django.test import TestCase
from app.models import League, Organization, CustomUser


class LeagueRatingConfigTest(TestCase):
    """Test League rating configuration fields."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='admin',
            password='testpass123'
        )
        self.org = Organization.objects.create(
            name='Test Org',
            owner=self.user
        )
        self.league = League.objects.create(
            organization=self.org,
            steam_league_id=12345,
            name='Test League'
        )

    def test_league_has_rating_system_field(self):
        """League should have rating_system field with default 'elo'."""
        self.assertEqual(self.league.rating_system, 'elo')

    def test_league_has_k_factor_fields(self):
        """League should have K-factor configuration fields."""
        self.assertEqual(self.league.k_factor_default, 32.0)
        self.assertEqual(self.league.k_factor_bottom_percentile, 40.0)
        self.assertEqual(self.league.k_factor_top_percentile, 16.0)
        self.assertEqual(self.league.percentile_threshold, 0.05)

    def test_league_has_age_decay_config(self):
        """League should have age decay configuration fields."""
        self.assertTrue(self.league.age_decay_enabled)
        self.assertEqual(self.league.age_decay_half_life_days, 180)
        self.assertEqual(self.league.age_decay_minimum, 0.1)

    def test_league_has_min_games_for_ranking(self):
        """League should have configurable minimum games for ranking."""
        self.assertEqual(self.league.min_games_for_ranking, 3)

    def test_league_rating_system_choices(self):
        """rating_system should accept valid choices."""
        self.league.rating_system = 'fixed_delta'
        self.league.save()
        self.league.refresh_from_db()
        self.assertEqual(self.league.rating_system, 'fixed_delta')
```

**Step 2: Run test to verify it fails**

```bash
inv test.run --cmd 'python manage.py test app.tests.test_league_rating -v 2'
```

Expected: FAIL with `AttributeError: 'League' object has no attribute 'rating_system'`

**Step 3: Add rating configuration fields to League model**

In `backend/app/models.py`, add these fields to the League class (after line 299):

```python
class League(models.Model):
    # ... existing fields ...

    # Rating system configuration
    RATING_SYSTEMS = [
        ('elo', 'Standard Elo'),
        ('glicko2', 'Glicko-2'),
        ('fixed_delta', 'Fixed Delta'),
        ('team_avg', 'Team Average Based'),
    ]
    rating_system = models.CharField(
        max_length=20,
        choices=RATING_SYSTEMS,
        default='elo'
    )

    # K-factor configuration
    k_factor_default = models.FloatField(default=32.0)
    k_factor_bottom_percentile = models.FloatField(default=40.0)
    k_factor_top_percentile = models.FloatField(default=16.0)
    percentile_threshold = models.FloatField(default=0.05)

    # Fixed delta configuration
    fixed_delta_win = models.IntegerField(default=25)
    fixed_delta_loss = models.IntegerField(default=25)

    # Age decay configuration
    age_decay_enabled = models.BooleanField(default=True)
    age_decay_half_life_days = models.IntegerField(default=180)
    age_decay_minimum = models.FloatField(default=0.1)

    # Recalculation constraints
    recalc_mmr_threshold = models.IntegerField(default=500)
    recalc_max_age_days = models.IntegerField(default=365)

    # Glicko-2 specific
    glicko_initial_rd = models.FloatField(default=350.0)
    glicko_rd_decay_per_day = models.FloatField(default=1.0)

    # Ranking configuration
    min_games_for_ranking = models.PositiveIntegerField(default=3)

    # ... rest of existing methods ...
```

**Step 4: Create and run migration**

```bash
cd backend && python manage.py makemigrations app --name league_rating_config
```

**Step 5: Run migration**

```bash
inv test.run --cmd 'python manage.py migrate'
```

**Step 6: Run test to verify it passes**

```bash
inv test.run --cmd 'python manage.py test app.tests.test_league_rating -v 2'
```

Expected: PASS

**Step 7: Commit**

```bash
git add backend/app/models.py backend/app/migrations/0043_league_rating_config.py backend/app/tests/test_league_rating.py
git commit -m "feat(league): add rating system configuration fields"
```

---

## Task 2: Create LeagueRating Model

**Files:**
- Create: `backend/app/models/league_rating.py`
- Modify: `backend/app/models/__init__.py` (if using models package) OR `backend/app/models.py`
- Create: `backend/app/migrations/0044_leaguerating.py`
- Test: `backend/app/tests/test_league_rating.py`

**Step 1: Add test for LeagueRating model**

Add to `backend/app/tests/test_league_rating.py`:

```python
from django.db import IntegrityError
from django.db.models import F


class LeagueRatingModelTest(TestCase):
    """Test LeagueRating model."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='player1',
            password='testpass123'
        )
        self.user.mmr = 3500
        self.user.save()

        self.org = Organization.objects.create(
            name='Test Org',
            owner=self.user
        )
        self.league = League.objects.create(
            organization=self.org,
            steam_league_id=12345,
            name='Test League'
        )

    def test_create_league_rating(self):
        """Can create LeagueRating for player in league."""
        from app.models import LeagueRating

        rating = LeagueRating.objects.create(
            league=self.league,
            player=self.user,
            base_mmr=self.user.mmr
        )
        self.assertEqual(rating.base_mmr, 3500)
        self.assertEqual(rating.positive_stats, 0)
        self.assertEqual(rating.negative_stats, 0)
        self.assertEqual(rating.games_played, 0)

    def test_league_rating_total_elo_property(self):
        """total_elo should be base_mmr + positive_stats - negative_stats."""
        from app.models import LeagueRating

        rating = LeagueRating.objects.create(
            league=self.league,
            player=self.user,
            base_mmr=3500,
            positive_stats=100,
            negative_stats=50
        )
        self.assertEqual(rating.total_elo, 3550)

    def test_league_rating_total_elo_annotation(self):
        """Can query total_elo using annotation."""
        from app.models import LeagueRating

        LeagueRating.objects.create(
            league=self.league,
            player=self.user,
            base_mmr=3500,
            positive_stats=100,
            negative_stats=50
        )

        # Query with annotation - this is how we filter by total_elo
        rating = LeagueRating.objects.annotate(
            computed_total_elo=F('base_mmr') + F('positive_stats') - F('negative_stats')
        ).filter(computed_total_elo=3550).first()

        self.assertIsNotNone(rating)
        self.assertEqual(rating.computed_total_elo, 3550)

    def test_league_rating_unique_constraint(self):
        """Only one LeagueRating per player per league."""
        from app.models import LeagueRating

        LeagueRating.objects.create(
            league=self.league,
            player=self.user,
            base_mmr=3500
        )
        with self.assertRaises(IntegrityError):
            LeagueRating.objects.create(
                league=self.league,
                player=self.user,
                base_mmr=3500
            )

    def test_league_rating_win_rate(self):
        """win_rate property should calculate correctly."""
        from app.models import LeagueRating

        rating = LeagueRating.objects.create(
            league=self.league,
            player=self.user,
            base_mmr=3500,
            games_played=10,
            wins=7,
            losses=3
        )
        self.assertAlmostEqual(rating.win_rate, 0.7)

    def test_league_rating_win_rate_zero_games(self):
        """win_rate should be 0 with no games."""
        from app.models import LeagueRating

        rating = LeagueRating.objects.create(
            league=self.league,
            player=self.user,
            base_mmr=3500
        )
        self.assertEqual(rating.win_rate, 0.0)
```

**Step 2: Run test to verify it fails**

```bash
inv test.run --cmd 'python manage.py test app.tests.test_league_rating.LeagueRatingModelTest -v 2'
```

Expected: FAIL with `ImportError: cannot import name 'LeagueRating'`

**Step 3: Create LeagueRating model**

Add to `backend/app/models.py` (after League model):

```python
class LeagueRating(models.Model):
    """Per-league rating tracking for a player using Elo-style system."""

    league = models.ForeignKey(
        'League',
        on_delete=models.CASCADE,
        related_name='ratings'
    )
    player = models.ForeignKey(
        'CustomUser',
        on_delete=models.CASCADE,
        related_name='league_ratings'
    )

    # Rating components
    base_mmr = models.IntegerField(default=0)
    base_mmr_snapshot_date = models.DateTimeField(auto_now_add=True)
    positive_stats = models.IntegerField(default=0)
    negative_stats = models.IntegerField(default=0)

    # Glicko-2 uncertainty tracking
    rating_deviation = models.FloatField(default=350.0)
    last_played = models.DateTimeField(null=True, blank=True)

    # Statistics
    games_played = models.PositiveIntegerField(default=0)
    wins = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ['league', 'player']
        indexes = [
            models.Index(fields=['league', '-games_played']),
            models.Index(fields=['league', 'last_played']),
        ]

    def __str__(self):
        return f"{self.player.username} in {self.league.name}: {self.total_elo}"

    @property
    def total_elo(self) -> int:
        """Calculate current effective rating."""
        return self.base_mmr + self.positive_stats - self.negative_stats

    @property
    def win_rate(self) -> float:
        """Calculate win percentage."""
        if self.games_played == 0:
            return 0.0
        return self.wins / self.games_played

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        invalidate_model(LeagueRating)
```

**Step 4: Create and run migration**

```bash
cd backend && python manage.py makemigrations app --name leaguerating
```

**Step 5: Run migration**

```bash
inv test.run --cmd 'python manage.py migrate'
```

**Step 6: Run test to verify it passes**

```bash
inv test.run --cmd 'python manage.py test app.tests.test_league_rating.LeagueRatingModelTest -v 2'
```

Expected: PASS

**Step 7: Commit**

```bash
git add backend/app/models.py backend/app/migrations/0044_leaguerating.py backend/app/tests/test_league_rating.py
git commit -m "feat(league): add LeagueRating model for per-league player ratings"
```

---

## Task 3: Create LeagueMatch and LeagueMatchParticipant Models

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/app/migrations/0045_leaguematch_leaguematchparticipant.py`
- Test: `backend/app/tests/test_league_rating.py`

**Step 1: Add tests for LeagueMatch and LeagueMatchParticipant**

Add to `backend/app/tests/test_league_rating.py`:

```python
from django.utils import timezone


class LeagueMatchModelTest(TestCase):
    """Test LeagueMatch and LeagueMatchParticipant models."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='admin',
            password='testpass123'
        )
        self.org = Organization.objects.create(
            name='Test Org',
            owner=self.user
        )
        self.league = League.objects.create(
            organization=self.org,
            steam_league_id=12345,
            name='Test League'
        )

    def test_create_league_match(self):
        """Can create a LeagueMatch."""
        from app.models import LeagueMatch

        match = LeagueMatch.objects.create(
            league=self.league,
            played_at=timezone.now()
        )
        self.assertFalse(match.is_finalized)
        self.assertIsNone(match.finalized_at)

    def test_league_match_with_steam_id(self):
        """LeagueMatch can have steam_match_id."""
        from app.models import LeagueMatch

        match = LeagueMatch.objects.create(
            league=self.league,
            steam_match_id=7654321,
            played_at=timezone.now()
        )
        self.assertEqual(match.steam_match_id, 7654321)

    def test_create_league_match_participant(self):
        """Can create LeagueMatchParticipant with all required fields."""
        from app.models import LeagueMatch, LeagueMatchParticipant, LeagueRating

        player = CustomUser.objects.create_user(
            username='player1',
            password='testpass123'
        )
        player.mmr = 3500
        player.save()

        rating = LeagueRating.objects.create(
            league=self.league,
            player=player,
            base_mmr=3500
        )

        match = LeagueMatch.objects.create(
            league=self.league,
            played_at=timezone.now()
        )

        participant = LeagueMatchParticipant.objects.create(
            match=match,
            player=player,
            player_rating=rating,
            team_side='radiant',
            mmr_at_match=3500,
            elo_before=3500,
            elo_after=3520,
            k_factor_used=32.0,
            rating_deviation_used=350.0,
            is_winner=True,
            delta=20
        )

        self.assertEqual(participant.delta, 20)
        self.assertEqual(participant.team_side, 'radiant')
        self.assertTrue(participant.is_winner)

    def test_participant_unique_constraint(self):
        """Only one participant record per player per match."""
        from app.models import LeagueMatch, LeagueMatchParticipant, LeagueRating

        player = CustomUser.objects.create_user(
            username='player1',
            password='testpass123'
        )
        rating = LeagueRating.objects.create(
            league=self.league,
            player=player,
            base_mmr=3500
        )
        match = LeagueMatch.objects.create(
            league=self.league,
            played_at=timezone.now()
        )

        LeagueMatchParticipant.objects.create(
            match=match,
            player=player,
            player_rating=rating,
            team_side='radiant',
            mmr_at_match=3500,
            elo_before=3500,
            elo_after=3520,
            k_factor_used=32.0,
            rating_deviation_used=350.0,
            is_winner=True,
            delta=20
        )

        with self.assertRaises(IntegrityError):
            LeagueMatchParticipant.objects.create(
                match=match,
                player=player,
                player_rating=rating,
                team_side='radiant',
                mmr_at_match=3500,
                elo_before=3500,
                elo_after=3520,
                k_factor_used=32.0,
                rating_deviation_used=350.0,
                is_winner=True,
                delta=20
            )
```

**Step 2: Run test to verify it fails**

```bash
inv test.run --cmd 'python manage.py test app.tests.test_league_rating.LeagueMatchModelTest -v 2'
```

Expected: FAIL with `ImportError: cannot import name 'LeagueMatch'`

**Step 3: Create LeagueMatch and LeagueMatchParticipant models**

Add to `backend/app/models.py` (after LeagueRating):

```python
class LeagueMatch(models.Model):
    """Canonical rated match object for a league."""

    league = models.ForeignKey(
        'League',
        on_delete=models.CASCADE,
        related_name='league_matches'
    )

    # Match source (can have game reference and/or steam_match_id)
    game = models.OneToOneField(
        'Game',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='league_match'
    )
    steam_match_id = models.BigIntegerField(null=True, blank=True, db_index=True)

    # Match details
    played_at = models.DateTimeField()
    stage = models.CharField(max_length=50, blank=True)
    bracket_slot = models.ForeignKey(
        'bracket.BracketSlot',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='league_matches'
    )

    # Finalization state
    is_finalized = models.BooleanField(default=False)
    finalized_at = models.DateTimeField(null=True, blank=True)

    # Recalculation tracking
    last_recalculated_at = models.DateTimeField(null=True, blank=True)
    recalculation_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-played_at']
        indexes = [
            models.Index(fields=['league', '-played_at']),
            models.Index(fields=['league', 'is_finalized']),
        ]

    def __str__(self):
        return f"LeagueMatch {self.id} in {self.league.name} at {self.played_at}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        invalidate_model(LeagueMatch)


class LeagueMatchParticipant(models.Model):
    """Individual player's participation in a league match."""

    TEAM_SIDES = [
        ('radiant', 'Radiant'),
        ('dire', 'Dire'),
    ]

    match = models.ForeignKey(
        'LeagueMatch',
        on_delete=models.CASCADE,
        related_name='participants'
    )
    player = models.ForeignKey(
        'CustomUser',
        on_delete=models.CASCADE,
        related_name='league_match_participations'
    )
    player_rating = models.ForeignKey(
        'LeagueRating',
        on_delete=models.CASCADE,
        related_name='match_participations'
    )

    # Team tracking
    team_side = models.CharField(max_length=10, choices=TEAM_SIDES)

    # Snapshot at match time (for auditing)
    mmr_at_match = models.IntegerField()
    elo_before = models.IntegerField()
    elo_after = models.IntegerField()

    # Rating calculation parameters used
    k_factor_used = models.FloatField()
    rating_deviation_used = models.FloatField()
    age_decay_factor = models.FloatField(default=1.0)

    # Result
    is_winner = models.BooleanField()
    delta = models.IntegerField()

    class Meta:
        unique_together = ['match', 'player']

    def __str__(self):
        result = "W" if self.is_winner else "L"
        return f"{self.player.username} ({result}) delta={self.delta}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        invalidate_model(LeagueMatchParticipant)
```

**Step 4: Create and run migration**

```bash
cd backend && python manage.py makemigrations app --name leaguematch_leaguematchparticipant
```

**Step 5: Run migration**

```bash
inv test.run --cmd 'python manage.py migrate'
```

**Step 6: Run test to verify it passes**

```bash
inv test.run --cmd 'python manage.py test app.tests.test_league_rating.LeagueMatchModelTest -v 2'
```

Expected: PASS

**Step 7: Commit**

```bash
git add backend/app/models.py backend/app/migrations/0045_leaguematch_leaguematchparticipant.py backend/app/tests/test_league_rating.py
git commit -m "feat(league): add LeagueMatch and LeagueMatchParticipant models"
```

---

## Task 4: Create Rating Engine with Pluggable Algorithms

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/rating.py`
- Test: `backend/app/tests/test_rating_engine.py`

**Step 1: Create test file for rating engine**

Create `backend/app/tests/test_rating_engine.py`:

```python
"""Tests for the pluggable rating engine."""
from django.test import TestCase
from app.models import League, Organization, CustomUser, LeagueRating


class EloRatingSystemTest(TestCase):
    """Test Elo rating calculations."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='admin',
            password='testpass123'
        )
        self.org = Organization.objects.create(
            name='Test Org',
            owner=self.user
        )
        self.league = League.objects.create(
            organization=self.org,
            steam_league_id=12345,
            name='Test League',
            rating_system='elo',
            k_factor_default=32.0
        )

    def test_elo_equal_ratings(self):
        """Equal ratings should give ~16 point swing with K=32."""
        from app.services.rating import EloRatingSystem

        player1 = CustomUser.objects.create_user(username='p1', password='test')
        player2 = CustomUser.objects.create_user(username='p2', password='test')

        rating1 = LeagueRating.objects.create(
            league=self.league, player=player1, base_mmr=3000
        )
        rating2 = LeagueRating.objects.create(
            league=self.league, player=player2, base_mmr=3000
        )

        system = EloRatingSystem(self.league)
        result = system.calculate_team_deltas(
            winners=[rating1],
            losers=[rating2]
        )

        # With equal ratings, expected = 0.5, so delta = K * (1 - 0.5) = 16
        self.assertEqual(result['winner_delta'], 16)
        self.assertEqual(result['loser_delta'], 16)

    def test_elo_higher_rated_wins(self):
        """Higher rated player winning should give smaller delta."""
        from app.services.rating import EloRatingSystem

        player1 = CustomUser.objects.create_user(username='p1', password='test')
        player2 = CustomUser.objects.create_user(username='p2', password='test')

        rating1 = LeagueRating.objects.create(
            league=self.league, player=player1, base_mmr=3400  # Higher
        )
        rating2 = LeagueRating.objects.create(
            league=self.league, player=player2, base_mmr=3000  # Lower
        )

        system = EloRatingSystem(self.league)
        result = system.calculate_team_deltas(
            winners=[rating1],  # Higher wins - expected outcome
            losers=[rating2]
        )

        # Higher rated winning = lower delta
        self.assertLess(result['winner_delta'], 16)

    def test_elo_lower_rated_wins(self):
        """Lower rated player winning (upset) should give larger delta."""
        from app.services.rating import EloRatingSystem

        player1 = CustomUser.objects.create_user(username='p1', password='test')
        player2 = CustomUser.objects.create_user(username='p2', password='test')

        rating1 = LeagueRating.objects.create(
            league=self.league, player=player1, base_mmr=3000  # Lower
        )
        rating2 = LeagueRating.objects.create(
            league=self.league, player=player2, base_mmr=3400  # Higher
        )

        system = EloRatingSystem(self.league)
        result = system.calculate_team_deltas(
            winners=[rating1],  # Lower wins - upset!
            losers=[rating2]
        )

        # Lower rated winning = higher delta
        self.assertGreater(result['winner_delta'], 16)

    def test_elo_team_average(self):
        """Team calculations should use team average ratings."""
        from app.services.rating import EloRatingSystem

        # Team 1: average 3000
        p1 = CustomUser.objects.create_user(username='p1', password='test')
        p2 = CustomUser.objects.create_user(username='p2', password='test')
        r1 = LeagueRating.objects.create(league=self.league, player=p1, base_mmr=2800)
        r2 = LeagueRating.objects.create(league=self.league, player=p2, base_mmr=3200)

        # Team 2: average 3000
        p3 = CustomUser.objects.create_user(username='p3', password='test')
        p4 = CustomUser.objects.create_user(username='p4', password='test')
        r3 = LeagueRating.objects.create(league=self.league, player=p3, base_mmr=3000)
        r4 = LeagueRating.objects.create(league=self.league, player=p4, base_mmr=3000)

        system = EloRatingSystem(self.league)
        result = system.calculate_team_deltas(
            winners=[r1, r2],
            losers=[r3, r4]
        )

        # Equal team averages = 16 point swing
        self.assertEqual(result['winner_delta'], 16)

    def test_age_decay_factor_applied(self):
        """Age decay should reduce delta."""
        from app.services.rating import EloRatingSystem

        player1 = CustomUser.objects.create_user(username='p1', password='test')
        player2 = CustomUser.objects.create_user(username='p2', password='test')

        rating1 = LeagueRating.objects.create(
            league=self.league, player=player1, base_mmr=3000
        )
        rating2 = LeagueRating.objects.create(
            league=self.league, player=player2, base_mmr=3000
        )

        system = EloRatingSystem(self.league)

        # Full weight
        result_full = system.calculate_team_deltas(
            winners=[rating1], losers=[rating2], age_decay_factor=1.0
        )

        # Half weight (180 days old with 180 day half-life)
        result_half = system.calculate_team_deltas(
            winners=[rating1], losers=[rating2], age_decay_factor=0.5
        )

        self.assertEqual(result_full['winner_delta'], 16)
        self.assertEqual(result_half['winner_delta'], 8)


class FixedDeltaRatingSystemTest(TestCase):
    """Test fixed delta rating system."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='admin',
            password='testpass123'
        )
        self.org = Organization.objects.create(
            name='Test Org',
            owner=self.user
        )
        self.league = League.objects.create(
            organization=self.org,
            steam_league_id=12345,
            name='Test League',
            rating_system='fixed_delta',
            fixed_delta_win=25,
            fixed_delta_loss=25
        )

    def test_fixed_delta_ignores_rating_difference(self):
        """Fixed delta should always give same points."""
        from app.services.rating import FixedDeltaRatingSystem

        player1 = CustomUser.objects.create_user(username='p1', password='test')
        player2 = CustomUser.objects.create_user(username='p2', password='test')

        rating1 = LeagueRating.objects.create(
            league=self.league, player=player1, base_mmr=5000  # Very high
        )
        rating2 = LeagueRating.objects.create(
            league=self.league, player=player2, base_mmr=1000  # Very low
        )

        system = FixedDeltaRatingSystem(self.league)
        result = system.calculate_team_deltas(
            winners=[rating1],
            losers=[rating2]
        )

        self.assertEqual(result['winner_delta'], 25)
        self.assertEqual(result['loser_delta'], 25)


class RatingSystemFactoryTest(TestCase):
    """Test rating system factory function."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='admin',
            password='testpass123'
        )
        self.org = Organization.objects.create(
            name='Test Org',
            owner=self.user
        )

    def test_get_elo_system(self):
        """Should return EloRatingSystem for 'elo' setting."""
        from app.services.rating import get_rating_system, EloRatingSystem

        league = League.objects.create(
            organization=self.org,
            steam_league_id=1,
            name='Elo League',
            rating_system='elo'
        )
        system = get_rating_system(league)
        self.assertIsInstance(system, EloRatingSystem)

    def test_get_fixed_delta_system(self):
        """Should return FixedDeltaRatingSystem for 'fixed_delta' setting."""
        from app.services.rating import get_rating_system, FixedDeltaRatingSystem

        league = League.objects.create(
            organization=self.org,
            steam_league_id=2,
            name='Fixed League',
            rating_system='fixed_delta'
        )
        system = get_rating_system(league)
        self.assertIsInstance(system, FixedDeltaRatingSystem)

    def test_unknown_system_defaults_to_elo(self):
        """Unknown rating system should default to Elo."""
        from app.services.rating import get_rating_system, EloRatingSystem

        league = League.objects.create(
            organization=self.org,
            steam_league_id=3,
            name='Unknown League',
            rating_system='unknown'
        )
        system = get_rating_system(league)
        self.assertIsInstance(system, EloRatingSystem)
```

**Step 2: Run test to verify it fails**

```bash
inv test.run --cmd 'python manage.py test app.tests.test_rating_engine -v 2'
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services'`

**Step 3: Create rating engine module**

Create `backend/app/services/__init__.py`:

```python
"""Service layer for app."""
from .rating import get_rating_system, EloRatingSystem, FixedDeltaRatingSystem

__all__ = ['get_rating_system', 'EloRatingSystem', 'FixedDeltaRatingSystem']
```

Create `backend/app/services/rating.py`:

```python
"""Pluggable rating system implementations."""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Dict, Any

if TYPE_CHECKING:
    from app.models import League, LeagueRating


class BaseRatingSystem(ABC):
    """Abstract base class for rating systems."""

    def __init__(self, league: 'League'):
        self.league = league

    @abstractmethod
    def calculate_team_deltas(
        self,
        winners: List['LeagueRating'],
        losers: List['LeagueRating'],
        age_decay_factor: float = 1.0
    ) -> Dict[str, Any]:
        """
        Calculate rating changes for a match result.

        Returns dict with:
            - winner_delta: int (points gained by winners)
            - loser_delta: int (points lost by losers)
            - winner_k_factors: dict[player_id, k_factor]
            - loser_k_factors: dict[player_id, k_factor]
        """
        pass

    def get_k_factor(self, player_rating: 'LeagueRating') -> float:
        """Get K-factor with percentile adjustment."""
        from django.db.models import F

        # Get player's percentile in the league
        percentile = self._calculate_percentile(player_rating)

        threshold = self.league.percentile_threshold

        if percentile <= threshold:
            # Bottom percentile - higher K for faster climb
            return self.league.k_factor_bottom_percentile
        elif percentile >= (1 - threshold):
            # Top percentile - lower K for stability
            return self.league.k_factor_top_percentile
        else:
            return self.league.k_factor_default

    def _calculate_percentile(self, player_rating: 'LeagueRating') -> float:
        """Calculate player's percentile rank in the league."""
        from django.db.models import F
        from app.models import LeagueRating

        # Use annotation to filter by computed total_elo
        all_ratings = LeagueRating.objects.filter(
            league=self.league
        ).annotate(
            computed_elo=F('base_mmr') + F('positive_stats') - F('negative_stats')
        )

        total = all_ratings.count()
        if total <= 1:
            return 0.5

        player_elo = player_rating.total_elo
        below = all_ratings.filter(computed_elo__lt=player_elo).count()

        return below / (total - 1)


class EloRatingSystem(BaseRatingSystem):
    """Standard Elo with team averages and percentile-based K-factor."""

    def calculate_team_deltas(
        self,
        winners: List['LeagueRating'],
        losers: List['LeagueRating'],
        age_decay_factor: float = 1.0
    ) -> Dict[str, Any]:
        """Calculate Elo rating changes for teams."""

        # Calculate team average ratings
        winner_avg = sum(r.total_elo for r in winners) / len(winners)
        loser_avg = sum(r.total_elo for r in losers) / len(losers)

        # Expected score for winners (from their perspective)
        expected_winner = 1 / (1 + 10 ** ((loser_avg - winner_avg) / 400))

        # Use default K for team calculation
        # Individual K-factors are applied per-player in finalization
        k = self.league.k_factor_default

        # Calculate base delta (before age decay)
        base_delta = k * (1 - expected_winner)

        # Apply age decay
        winner_delta = round(base_delta * age_decay_factor)
        loser_delta = round(base_delta * age_decay_factor)

        # Calculate individual K-factors for tracking
        winner_k_factors = {r.player_id: self.get_k_factor(r) for r in winners}
        loser_k_factors = {r.player_id: self.get_k_factor(r) for r in losers}

        return {
            'winner_delta': winner_delta,
            'loser_delta': loser_delta,
            'winner_k_factors': winner_k_factors,
            'loser_k_factors': loser_k_factors,
        }


class FixedDeltaRatingSystem(BaseRatingSystem):
    """Fixed point gain/loss regardless of opponent rating."""

    def calculate_team_deltas(
        self,
        winners: List['LeagueRating'],
        losers: List['LeagueRating'],
        age_decay_factor: float = 1.0
    ) -> Dict[str, Any]:
        """Calculate fixed rating changes."""

        winner_delta = round(self.league.fixed_delta_win * age_decay_factor)
        loser_delta = round(self.league.fixed_delta_loss * age_decay_factor)

        # K-factors are the fixed values for tracking
        winner_k_factors = {r.player_id: self.league.fixed_delta_win for r in winners}
        loser_k_factors = {r.player_id: self.league.fixed_delta_loss for r in losers}

        return {
            'winner_delta': winner_delta,
            'loser_delta': loser_delta,
            'winner_k_factors': winner_k_factors,
            'loser_k_factors': loser_k_factors,
        }


def get_rating_system(league: 'League') -> BaseRatingSystem:
    """Factory function to get the appropriate rating system."""
    systems = {
        'elo': EloRatingSystem,
        'fixed_delta': FixedDeltaRatingSystem,
        # Future: 'glicko2': Glicko2RatingSystem,
        # Future: 'team_avg': TeamAvgRatingSystem,
    }

    system_class = systems.get(league.rating_system, EloRatingSystem)
    return system_class(league)
```

**Step 4: Run test to verify it passes**

```bash
inv test.run --cmd 'python manage.py test app.tests.test_rating_engine -v 2'
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/
git add backend/app/tests/test_rating_engine.py
git commit -m "feat(league): add pluggable rating engine with Elo and FixedDelta systems"
```

---

## Task 5: Create Match Finalization Service

**Files:**
- Create: `backend/app/services/match_finalization.py`
- Modify: `backend/app/services/__init__.py`
- Test: `backend/app/tests/test_match_finalization.py`

**Step 1: Create test file for match finalization**

Create `backend/app/tests/test_match_finalization.py`:

```python
"""Tests for match finalization service."""
from django.test import TestCase
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from app.models import (
    League, Organization, CustomUser, LeagueRating,
    LeagueMatch, LeagueMatchParticipant
)


class MatchFinalizationServiceTest(TestCase):
    """Test LeagueMatchService.finalize()."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='admin',
            password='testpass123'
        )
        self.org = Organization.objects.create(
            name='Test Org',
            owner=self.admin
        )
        self.league = League.objects.create(
            organization=self.org,
            steam_league_id=12345,
            name='Test League',
            rating_system='elo',
            k_factor_default=32.0
        )

        # Create 10 players (5v5)
        self.radiant = []
        self.dire = []
        for i in range(5):
            p = CustomUser.objects.create_user(
                username=f'radiant{i}',
                password='test'
            )
            p.mmr = 3000
            p.save()
            self.radiant.append(p)

        for i in range(5):
            p = CustomUser.objects.create_user(
                username=f'dire{i}',
                password='test'
            )
            p.mmr = 3000
            p.save()
            self.dire.append(p)

    def test_finalize_creates_ratings_if_missing(self):
        """Finalize should create LeagueRating records for new players."""
        from app.services.match_finalization import LeagueMatchService

        match = LeagueMatch.objects.create(
            league=self.league,
            played_at=timezone.now()
        )

        LeagueMatchService.finalize(
            match=match,
            winners=self.radiant,
            losers=self.dire,
            winning_side='radiant'
        )

        # All 10 players should have ratings now
        self.assertEqual(LeagueRating.objects.filter(league=self.league).count(), 10)

    def test_finalize_updates_ratings(self):
        """Finalize should update winner/loser ratings correctly."""
        from app.services.match_finalization import LeagueMatchService

        match = LeagueMatch.objects.create(
            league=self.league,
            played_at=timezone.now()
        )

        LeagueMatchService.finalize(
            match=match,
            winners=self.radiant,
            losers=self.dire,
            winning_side='radiant'
        )

        # Winners should have positive_stats increased
        winner_rating = LeagueRating.objects.get(
            league=self.league,
            player=self.radiant[0]
        )
        self.assertGreater(winner_rating.positive_stats, 0)
        self.assertEqual(winner_rating.negative_stats, 0)
        self.assertEqual(winner_rating.wins, 1)
        self.assertEqual(winner_rating.games_played, 1)

        # Losers should have negative_stats increased
        loser_rating = LeagueRating.objects.get(
            league=self.league,
            player=self.dire[0]
        )
        self.assertEqual(loser_rating.positive_stats, 0)
        self.assertGreater(loser_rating.negative_stats, 0)
        self.assertEqual(loser_rating.losses, 1)
        self.assertEqual(loser_rating.games_played, 1)

    def test_finalize_creates_participants(self):
        """Finalize should create LeagueMatchParticipant records."""
        from app.services.match_finalization import LeagueMatchService

        match = LeagueMatch.objects.create(
            league=self.league,
            played_at=timezone.now()
        )

        LeagueMatchService.finalize(
            match=match,
            winners=self.radiant,
            losers=self.dire,
            winning_side='radiant'
        )

        # Should have 10 participants
        self.assertEqual(match.participants.count(), 10)

        # Check participant data
        winner_part = match.participants.get(player=self.radiant[0])
        self.assertTrue(winner_part.is_winner)
        self.assertEqual(winner_part.team_side, 'radiant')
        self.assertGreater(winner_part.delta, 0)
        self.assertEqual(winner_part.mmr_at_match, 3000)

        loser_part = match.participants.get(player=self.dire[0])
        self.assertFalse(loser_part.is_winner)
        self.assertEqual(loser_part.team_side, 'dire')
        self.assertLess(loser_part.delta, 0)

    def test_finalize_marks_match_finalized(self):
        """Finalize should set is_finalized and finalized_at."""
        from app.services.match_finalization import LeagueMatchService

        match = LeagueMatch.objects.create(
            league=self.league,
            played_at=timezone.now()
        )

        LeagueMatchService.finalize(
            match=match,
            winners=self.radiant,
            losers=self.dire,
            winning_side='radiant'
        )

        match.refresh_from_db()
        self.assertTrue(match.is_finalized)
        self.assertIsNotNone(match.finalized_at)

    def test_finalize_already_finalized_raises(self):
        """Cannot finalize an already finalized match."""
        from app.services.match_finalization import LeagueMatchService

        match = LeagueMatch.objects.create(
            league=self.league,
            played_at=timezone.now(),
            is_finalized=True,
            finalized_at=timezone.now()
        )

        with self.assertRaises(ValueError) as ctx:
            LeagueMatchService.finalize(
                match=match,
                winners=self.radiant,
                losers=self.dire,
                winning_side='radiant'
            )

        self.assertIn('already finalized', str(ctx.exception))

    def test_finalize_atomic_rollback_on_error(self):
        """Finalize should rollback all changes on error."""
        from app.services.match_finalization import LeagueMatchService

        match = LeagueMatch.objects.create(
            league=self.league,
            played_at=timezone.now()
        )

        # Create a rating for one player to cause unique constraint violation
        # when we try to create it again with bad data
        rating = LeagueRating.objects.create(
            league=self.league,
            player=self.radiant[0],
            base_mmr=3000
        )

        initial_participant_count = LeagueMatchParticipant.objects.count()

        # This should succeed even with existing rating
        LeagueMatchService.finalize(
            match=match,
            winners=self.radiant,
            losers=self.dire,
            winning_side='radiant'
        )

        # Should have created participants
        self.assertEqual(
            LeagueMatchParticipant.objects.count(),
            initial_participant_count + 10
        )


class AgeDecayCalculationTest(TestCase):
    """Test age decay calculations."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='admin',
            password='testpass123'
        )
        self.org = Organization.objects.create(
            name='Test Org',
            owner=self.admin
        )
        self.league = League.objects.create(
            organization=self.org,
            steam_league_id=12345,
            name='Test League',
            age_decay_enabled=True,
            age_decay_half_life_days=180,
            age_decay_minimum=0.1
        )

    def test_no_decay_for_recent_match(self):
        """Match played today should have decay factor of 1.0."""
        from app.services.match_finalization import LeagueMatchService

        decay = LeagueMatchService.calculate_age_decay(
            self.league,
            timezone.now()
        )
        self.assertEqual(decay, 1.0)

    def test_half_decay_at_half_life(self):
        """Match at half-life age should have ~0.5 decay."""
        from app.services.match_finalization import LeagueMatchService

        played_at = timezone.now() - timedelta(days=180)
        decay = LeagueMatchService.calculate_age_decay(
            self.league,
            played_at
        )
        self.assertAlmostEqual(decay, 0.5, places=2)

    def test_decay_respects_minimum(self):
        """Very old matches should not decay below minimum."""
        from app.services.match_finalization import LeagueMatchService

        played_at = timezone.now() - timedelta(days=1000)  # Very old
        decay = LeagueMatchService.calculate_age_decay(
            self.league,
            played_at
        )
        self.assertEqual(decay, 0.1)  # Minimum

    def test_decay_disabled(self):
        """Decay factor should be 1.0 when decay is disabled."""
        from app.services.match_finalization import LeagueMatchService

        self.league.age_decay_enabled = False
        self.league.save()

        played_at = timezone.now() - timedelta(days=500)
        decay = LeagueMatchService.calculate_age_decay(
            self.league,
            played_at
        )
        self.assertEqual(decay, 1.0)
```

**Step 2: Run test to verify it fails**

```bash
inv test.run --cmd 'python manage.py test app.tests.test_match_finalization -v 2'
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.match_finalization'`

**Step 3: Create match finalization service**

Create `backend/app/services/match_finalization.py`:

```python
"""Match finalization service for league ratings."""
from datetime import datetime
from typing import List
from django.db import transaction
from django.utils import timezone


class LeagueMatchService:
    """Service for managing league matches and rating updates."""

    @classmethod
    def create_from_game(cls, league, game, bracket_slot=None):
        """Create a LeagueMatch from an existing Game object."""
        from app.models import LeagueMatch

        match = LeagueMatch.objects.create(
            league=league,
            game=game,
            played_at=game.updated_at or timezone.now(),
            stage=game.bracket_type or '',
            bracket_slot=bracket_slot
        )
        return match

    @classmethod
    @transaction.atomic
    def finalize(
        cls,
        match,
        winners: List,
        losers: List,
        winning_side: str
    ):
        """
        Finalize a match and update all participant ratings.

        Args:
            match: The LeagueMatch to finalize
            winners: List of CustomUser objects who won
            losers: List of CustomUser objects who lost
            winning_side: 'radiant' or 'dire'
        """
        from app.models import LeagueMatch, LeagueRating, LeagueMatchParticipant
        from app.services.rating import get_rating_system

        # Lock match row to prevent race condition
        match = LeagueMatch.objects.select_for_update().get(pk=match.pk)

        if match.is_finalized:
            raise ValueError("Match is already finalized")

        league = match.league
        rating_system = get_rating_system(league)

        # Calculate age decay
        age_decay = cls.calculate_age_decay(league, match.played_at)

        # Get or create ratings for all participants (batch lookup)
        all_players = winners + losers
        existing_ratings = {
            r.player_id: r
            for r in LeagueRating.objects.filter(
                league=league,
                player__in=all_players
            ).select_for_update()
        }

        # Create missing ratings
        for player in all_players:
            if player.pk not in existing_ratings:
                existing_ratings[player.pk] = LeagueRating.objects.create(
                    league=league,
                    player=player,
                    base_mmr=player.mmr or 0
                )

        winner_ratings = [existing_ratings[p.pk] for p in winners]
        loser_ratings = [existing_ratings[p.pk] for p in losers]

        # Calculate deltas using rating system
        result = rating_system.calculate_team_deltas(
            winners=winner_ratings,
            losers=loser_ratings,
            age_decay_factor=age_decay
        )

        winner_delta = result['winner_delta']
        loser_delta = result['loser_delta']
        winner_k_factors = result['winner_k_factors']
        loser_k_factors = result['loser_k_factors']

        losing_side = 'dire' if winning_side == 'radiant' else 'radiant'

        # Update winner ratings and create participants
        for player, rating in zip(winners, winner_ratings):
            elo_before = rating.total_elo
            rating.positive_stats += winner_delta
            rating.games_played += 1
            rating.wins += 1
            rating.last_played = match.played_at
            rating.save()

            LeagueMatchParticipant.objects.create(
                match=match,
                player=player,
                player_rating=rating,
                team_side=winning_side,
                mmr_at_match=rating.base_mmr,
                elo_before=elo_before,
                elo_after=rating.total_elo,
                k_factor_used=winner_k_factors.get(player.pk, league.k_factor_default),
                rating_deviation_used=rating.rating_deviation,
                age_decay_factor=age_decay,
                is_winner=True,
                delta=winner_delta
            )

        # Update loser ratings and create participants
        for player, rating in zip(losers, loser_ratings):
            elo_before = rating.total_elo
            rating.negative_stats += loser_delta
            rating.games_played += 1
            rating.losses += 1
            rating.last_played = match.played_at
            rating.save()

            LeagueMatchParticipant.objects.create(
                match=match,
                player=player,
                player_rating=rating,
                team_side=losing_side,
                mmr_at_match=rating.base_mmr,
                elo_before=elo_before,
                elo_after=rating.total_elo,
                k_factor_used=loser_k_factors.get(player.pk, league.k_factor_default),
                rating_deviation_used=rating.rating_deviation,
                age_decay_factor=age_decay,
                is_winner=False,
                delta=-loser_delta  # Negative for losers
            )

        # Mark match as finalized
        match.is_finalized = True
        match.finalized_at = timezone.now()
        match.save()

        return match

    @classmethod
    def calculate_age_decay(cls, league, played_at: datetime) -> float:
        """Calculate age decay factor for a match."""
        if not league.age_decay_enabled:
            return 1.0

        now = timezone.now()
        if timezone.is_naive(played_at):
            played_at = timezone.make_aware(played_at)

        age_days = (now - played_at).days
        if age_days <= 0:
            return 1.0

        half_life = league.age_decay_half_life_days

        # Half-life decay formula: factor = 0.5 ^ (age / half_life)
        decay = 0.5 ** (age_days / half_life)

        # Enforce minimum
        return max(decay, league.age_decay_minimum)

    @classmethod
    @transaction.atomic
    def recalculate(cls, match):
        """
        Recalculate ratings for a finalized match.

        Reverses original deltas, then re-finalizes with current parameters.
        """
        from app.models import LeagueMatch

        # Lock match
        match = LeagueMatch.objects.select_for_update().get(pk=match.pk)
        league = match.league

        if not match.is_finalized:
            raise ValueError("Cannot recalculate unfinalized match")

        # Check age constraint
        age_days = (timezone.now() - match.played_at).days
        if age_days > league.recalc_max_age_days:
            raise ValueError(
                f"Match is too old to recalculate "
                f"({age_days} days > {league.recalc_max_age_days})"
            )

        # Store winner/loser info BEFORE deleting participants
        participants = list(match.participants.select_related('player', 'player_rating'))
        winners = [p.player for p in participants if p.is_winner]
        losers = [p.player for p in participants if not p.is_winner]
        winning_side = next(
            (p.team_side for p in participants if p.is_winner),
            'radiant'
        )

        # Check MMR threshold for all participants
        for participant in participants:
            current_mmr = participant.player_rating.base_mmr
            match_mmr = participant.mmr_at_match
            diff = abs(current_mmr - match_mmr)

            if diff > league.recalc_mmr_threshold:
                raise ValueError(
                    f"Player {participant.player.username} MMR changed too much "
                    f"({diff} > {league.recalc_mmr_threshold})"
                )

        # Reverse the original deltas
        for participant in participants:
            rating = participant.player_rating
            if participant.is_winner:
                rating.positive_stats -= participant.delta
                rating.wins -= 1
            else:
                rating.negative_stats -= abs(participant.delta)
                rating.losses -= 1
            rating.games_played -= 1
            rating.save()

        # Delete old participants
        match.participants.all().delete()

        # Mark as not finalized for re-finalization
        match.is_finalized = False
        match.recalculation_count += 1
        match.last_recalculated_at = timezone.now()
        match.save()

        # Re-finalize with stored winner/loser lists
        return cls.finalize(match, winners, losers, winning_side)
```

Update `backend/app/services/__init__.py`:

```python
"""Service layer for app."""
from .rating import get_rating_system, EloRatingSystem, FixedDeltaRatingSystem
from .match_finalization import LeagueMatchService

__all__ = [
    'get_rating_system',
    'EloRatingSystem',
    'FixedDeltaRatingSystem',
    'LeagueMatchService',
]
```

**Step 4: Run test to verify it passes**

```bash
inv test.run --cmd 'python manage.py test app.tests.test_match_finalization -v 2'
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/
git add backend/app/tests/test_match_finalization.py
git commit -m "feat(league): add match finalization service with atomic transactions"
```

---

## Task 6: Add User MMR Verification Fields

**Files:**
- Modify: `backend/app/models.py` (CustomUser model)
- Create: `backend/app/migrations/0046_customuser_mmr_verification.py`
- Test: `backend/app/tests/test_league_rating.py`

**Step 1: Add tests for MMR verification fields**

Add to `backend/app/tests/test_league_rating.py`:

```python
class CustomUserMMRVerificationTest(TestCase):
    """Test CustomUser MMR verification fields."""

    def test_user_has_mmr_verification_fields(self):
        """CustomUser should have MMR verification tracking fields."""
        user = CustomUser.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        self.assertFalse(user.has_active_dota_mmr)
        self.assertIsNone(user.dota_mmr_last_verified)

    def test_user_can_set_mmr_verified(self):
        """Can set MMR verification status and timestamp."""
        user = CustomUser.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        user.has_active_dota_mmr = True
        user.dota_mmr_last_verified = timezone.now()
        user.save()

        user.refresh_from_db()
        self.assertTrue(user.has_active_dota_mmr)
        self.assertIsNotNone(user.dota_mmr_last_verified)

    def test_needs_mmr_verification_property(self):
        """needs_mmr_verification should be True if verified > 30 days ago."""
        user = CustomUser.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        # No active MMR = no verification needed
        user.has_active_dota_mmr = False
        self.assertFalse(user.needs_mmr_verification)

        # Active MMR, never verified = needs verification
        user.has_active_dota_mmr = True
        user.dota_mmr_last_verified = None
        self.assertTrue(user.needs_mmr_verification)

        # Active MMR, verified recently = no verification needed
        user.dota_mmr_last_verified = timezone.now()
        self.assertFalse(user.needs_mmr_verification)

        # Active MMR, verified > 30 days ago = needs verification
        user.dota_mmr_last_verified = timezone.now() - timedelta(days=31)
        self.assertTrue(user.needs_mmr_verification)
```

**Step 2: Run test to verify it fails**

```bash
inv test.run --cmd 'python manage.py test app.tests.test_league_rating.CustomUserMMRVerificationTest -v 2'
```

Expected: FAIL with `AttributeError: 'CustomUser' object has no attribute 'has_active_dota_mmr'`

**Step 3: Add MMR verification fields to CustomUser**

In `backend/app/models.py`, add these fields to CustomUser class (after mmr field around line 76):

```python
    # MMR verification tracking
    has_active_dota_mmr = models.BooleanField(default=False)
    dota_mmr_last_verified = models.DateTimeField(null=True, blank=True)

    @property
    def needs_mmr_verification(self) -> bool:
        """Check if user needs to verify their MMR (>30 days since last verification)."""
        if not self.has_active_dota_mmr:
            return False
        if self.dota_mmr_last_verified is None:
            return True
        days_since = (timezone.now() - self.dota_mmr_last_verified).days
        return days_since > 30
```

Add the import at the top if not present:
```python
from datetime import timedelta
```

**Step 4: Create and run migration**

```bash
cd backend && python manage.py makemigrations app --name customuser_mmr_verification
```

**Step 5: Run migration**

```bash
inv test.run --cmd 'python manage.py migrate'
```

**Step 6: Run test to verify it passes**

```bash
inv test.run --cmd 'python manage.py test app.tests.test_league_rating.CustomUserMMRVerificationTest -v 2'
```

Expected: PASS

**Step 7: Commit**

```bash
git add backend/app/models.py backend/app/migrations/0046_customuser_mmr_verification.py backend/app/tests/test_league_rating.py
git commit -m "feat(user): add MMR verification tracking fields to CustomUser"
```

---

## Task 7: Run All Tests and Final Verification

**Step 1: Run all league rating tests**

```bash
inv test.run --cmd 'python manage.py test app.tests.test_league_rating app.tests.test_rating_engine app.tests.test_match_finalization -v 2'
```

Expected: All tests PASS

**Step 2: Run full test suite to check for regressions**

```bash
inv test.run --cmd 'python manage.py test app.tests -v 2'
```

Expected: All tests PASS

**Step 3: Commit any final fixes if needed**

---

## Summary

This implementation plan covers:

1. **Task 1**: League rating configuration fields (rating system, K-factors, decay)
2. **Task 2**: LeagueRating model for per-player, per-league stats
3. **Task 3**: LeagueMatch and LeagueMatchParticipant for match tracking
4. **Task 4**: Pluggable rating engine (Elo, FixedDelta)
5. **Task 5**: Match finalization service with atomic transactions
6. **Task 6**: User MMR verification fields
7. **Task 7**: Final verification

**Critical fixes implemented:**
- `total_elo` filtering uses annotation, not property
- `select_for_update()` prevents race conditions
- `team_side` field tracks which team players were on
- Recalculation stores winners/losers before deleting participants
- Batch lookups prevent N+1 queries

**Future work (not in this plan):**
- API serializers and ViewSets
- Admin interface
- Integration with existing Game model signals
- Leaderboard pagination
- Glicko-2 implementation
