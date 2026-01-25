# League Rating System

A comprehensive rating system for tracking player skill across tournaments and leagues within DraftForge.

## Overview

The league rating system tracks player performance with two parallel rating methods, handles significant MMR changes through epochs, and aggregates data across organizations for reliable skill assessment.

---

## Features

### Dual Rating System

The system tracks **two parallel ratings** for each player:

| Rating Type | Purpose | Best For |
|-------------|---------|----------|
| **Elo-style** | Simple, intuitive number anchored to Dota 2 MMR | Display, quick comparisons |
| **Glicko-2** | Statistical rating with uncertainty tracking | Accurate matchmaking, reliability assessment |

**Why both?** Elo is familiar to players and anchors to their real MMR. Glicko-2 provides mathematical confidence in ratings, especially important for players with few games.

---

### MMR Epoch System

**Problem:** Player joins at 1000 MMR, earns +200 rating over 10 games. A year later their Dota MMR is 5000. Should +200 points from playing 1000 MMR opponents count toward their 5000 MMR rating?

**Solution:** When a player's verified MMR changes significantly (default: 1000+ difference), a new "epoch" begins:

- Previous rating data is archived (not deleted)
- Fresh rating starts from new MMR baseline
- Historical data remains accessible for reference

This ensures ratings reflect **current skill level**, not accumulated points from outdated games.

---

### Flexible K-Factor Modes

K-factor determines how much each match affects a player's rating. Four modes available:

| Mode | Behavior | Use Case |
|------|----------|----------|
| **Fixed** | Same K for everyone | Simple, predictable leagues |
| **Placement** | Higher K for first N games | New player calibration |
| **Percentile** | Higher K for bottom players, lower for top | Encourages climb, protects top ranks |
| **Hybrid** | Placement first, then percentile | Most balanced (recommended default) |

This allows leagues to tune rating volatility based on their format and goals.

---

### Organization-Level Rating Aggregation

**Problem:** Organizations run many small leagues (weekly 8-player tournaments). Individual leagues have too few games for reliable ratings.

**Solution:** Aggregate ratings across all leagues in an organization:

- Combines data from multiple leagues
- Weighted by games played and recency
- Provides organization-wide leaderboard
- Shows reliability indicator (10+ games OR 3+ games across 3+ leagues)

**Aggregation Methods:**

- **Weighted Average** - Leagues weighted by games and recency
- **Bayesian Combination** - Statistical combination using confidence
- **Most Recent** - Use latest league's rating, sum stats

---

### Age Decay for Matches

**Problem:** Matches from 2 years ago shouldn't count as much as recent matches.

**Solution:** Configurable half-life decay:

- Older matches contribute less to rating changes
- Configurable half-life (default: 180 days = 50% weight)
- Minimum floor (default: 10% - matches never become worthless)
- Can be disabled entirely per league

---

### Rating Deviation (Uncertainty Tracking)

**Problem:** A player with 3 games and a player with 100 games may have the same rating, but we're much more confident in the 100-game player.

**Solution:** Glicko-2's Rating Deviation (RD):

- High RD = high uncertainty, larger rating swings
- Low RD = high confidence, smaller swings
- RD increases with inactivity (uncertainty grows without data)
- Displayed as confidence interval in UI

---

### Configurable Display Options

Leagues can choose which rating to show:

- **Total Elo** - `base_mmr + positive - negative`
- **Net Change** - `positive - negative` (hides base MMR)
- **Glicko Rating** - Statistical rating without MMR anchor

This accommodates different league cultures and player preferences.

---

## Design Decisions

### Separate Configuration Model

Rating config lives in a dedicated model, not embedded in League:

- Separation of concerns
- Leagues without ratings don't carry config baggage
- Enables future config versioning
- All defaults defined in ENUMs, not magic numbers

### Pluggable Rating Algorithms

Rating calculation uses strategy pattern:

- **EloRatingSystem** - Standard Elo with percentile K-factors
- **FixedDeltaRatingSystem** - Flat points per win/loss
- **Glicko2RatingSystem** - Full Glicko-2 implementation

New algorithms can be added without modifying existing code.

### Match Participant Snapshots

Every match records:

- MMR at match time
- Rating before/after
- K-factor and parameters used
- Age decay applied

This enables:

- Auditing rating changes
- Recalculation with constraints
- Historical analysis

---

## Problems and Solutions

| Problem | Solution |
|---------|----------|
| Outdated MMR distorts ratings | MMR Epoch system resets on significant changes |
| New players swing too much/too little | Placement game K-factor mode |
| Top players lose too much to lower ranks | Percentile-based K-factor scaling |
| Small leagues lack data for reliable ratings | Organization-level aggregation |
| Old matches overweighted | Age decay with configurable half-life |
| Uncertainty not visible | Rating Deviation display and confidence intervals |
| Different leagues need different rules | Fully configurable per-league settings |
| Rating changes hard to audit | Comprehensive match participant snapshots |

---

## Metrics Tracked

### Per Player Per League

- Base MMR (Dota 2 anchor)
- Positive/Negative stat accumulation
- Glicko-2 rating, RD, volatility
- Games/Wins/Losses
- Current epoch number
- Last played timestamp

### Per Organization Per Player

- Aggregated rating across all org leagues
- Total games/wins/losses across org
- Leagues participated count
- Reliability indicator

### Per Match Per Participant

- Rating before/after
- K-factor used
- Age decay applied
- RD at calculation time
- Win/loss result and delta

---

## Configuration Defaults

| Setting | Default | Description |
|---------|---------|-------------|
| K-factor (default) | 32 | Standard rating swing |
| K-factor (placement) | 64 | Higher volatility for new players |
| K-factor (bottom 5%) | 40 | Faster climb for low-rated players |
| K-factor (top 5%) | 16 | More stability for top players |
| Placement games | 10 | Games before standard K applies |
| Min games for ranking | 3 | Required to appear on leaderboard |
| Age decay half-life | 180 days | When matches count 50% |
| Glicko initial RD | 350 | Starting uncertainty |
| MMR epoch threshold | 1000 | MMR change triggering reset |

All defaults stored in `RatingDefaults` enum - no magic numbers in code.
