# Draft System

The draft system allows tournament captains to pick players for their teams. Three draft styles are available, each with different pick order mechanics.

## Draft Styles

### Snake Draft

The classic snake draft where pick order reverses each round.

**Pick Pattern (4 teams):**
```
Round 1: Team 1 → Team 2 → Team 3 → Team 4
Round 2: Team 4 → Team 3 → Team 2 → Team 1
Round 3: Team 1 → Team 2 → Team 3 → Team 4
Round 4: Team 4 → Team 3 → Team 2 → Team 1
```

**Characteristics:**

- Predictable pick order
- First pick team gets picks 1, 8, 9, 16
- Last pick team gets picks 4, 5, 12, 13
- Good balance between first and last pick advantage

### Normal Draft

Standard draft where pick order stays the same each round.

**Pick Pattern (4 teams):**
```
Round 1: Team 1 → Team 2 → Team 3 → Team 4
Round 2: Team 1 → Team 2 → Team 3 → Team 4
Round 3: Team 1 → Team 2 → Team 3 → Team 4
Round 4: Team 1 → Team 2 → Team 3 → Team 4
```

**Characteristics:**

- Simple, predictable order
- First pick team has significant advantage
- Last pick team may struggle with player availability

### Shuffle Draft

Dynamic draft where the team with the lowest total MMR always picks next.

**How It Works:**

1. Before each pick, calculate total MMR for each team (captain + all picked members)
2. Team with lowest total MMR picks next
3. If teams are tied, a dice roll determines who picks

**Tie-Breaking:**

When multiple teams have the same lowest MMR:

1. Each tied team rolls a d6 (1-6)
2. Highest roll wins and picks next
3. If rolls tie, re-roll only among still-tied teams
4. Continue until one winner

**Example:**
```
Team A (15,400 MMR) rolls: 4
Team B (15,400 MMR) rolls: 4
Team C (15,400 MMR) rolls: 2

→ Team C eliminated, A and B re-roll

Team A rolls: 3
Team B rolls: 5

→ Team B wins, picks next
```

**Characteristics:**

- Self-balancing - weaker teams get priority picks
- Unpredictable order until draft starts
- Tie-breaker adds excitement
- Cannot simulate final team MMRs in advance

## Draft Style Modal

The Draft Style modal allows admins to:

1. View all draft style options
2. Compare predicted team balance for Snake vs Normal
3. See that Shuffle is dynamic and cannot be predicted
4. Select and apply a draft style

## Data Models

### Draft

| Field | Type | Description |
|-------|------|-------------|
| `tournament` | ForeignKey | Associated tournament |
| `draft_style` | CharField | `snake`, `normal`, or `shuffle` |

### DraftRound

| Field | Type | Description |
|-------|------|-------------|
| `draft` | ForeignKey | Parent draft |
| `captain` | ForeignKey | Captain making the pick |
| `pick_number` | Integer | Sequential pick number (1, 2, 3...) |
| `pick_phase` | Integer | Phase/round of the draft |
| `choice` | ForeignKey | Player selected (null until picked) |
| `was_tie` | Boolean | Whether tie-breaking was needed |
| `tie_roll_data` | JSONField | Tie resolution details |

### tie_roll_data Structure

When a tie occurs in Shuffle draft, the `tie_roll_data` field contains:

```json
{
  "tied_teams": [
    {"id": 1, "name": "Team Alpha", "mmr": 15400},
    {"id": 2, "name": "Team Beta", "mmr": 15400}
  ],
  "roll_rounds": [
    [
      {"team_id": 1, "roll": 4},
      {"team_id": 2, "roll": 4}
    ],
    [
      {"team_id": 1, "roll": 3},
      {"team_id": 2, "roll": 5}
    ]
  ],
  "winner_id": 2
}
```

## API Endpoints

### Pick Player

```
POST /api/tournaments/{id}/draft/pick/
```

**Request:**
```json
{
  "player_id": 123
}
```

**Response (Shuffle Draft with tie):**
```json
{
  "success": true,
  "tournament": { ... },
  "next_pick": {
    "captain_id": 5,
    "team_id": 2,
    "team_name": "Team Beta",
    "team_mmr": 15400
  },
  "tie_resolution": {
    "tied_teams": [...],
    "roll_rounds": [...],
    "winner_id": 2
  }
}
```

### Update Draft Style

```
PUT /api/drafts/{id}/
```

**Request:**
```json
{
  "draft_style": "shuffle"
}
```

## Frontend Components

### TieResolutionOverlay

Displays when a tie occurs during Shuffle draft:

- Shows all tied teams with their MMR
- Displays each round of dice rolls
- Highlights the winner
- "Continue" button to proceed

### DraftStyleModal

Allows selecting draft style:

- Snake Draft option with predicted MMR balance
- Normal Draft option with predicted MMR balance
- Shuffle Draft option (dynamic balance, no prediction)
- Apply button to change style

## Implementation Notes

### Snake/Normal vs Shuffle

| Aspect | Snake/Normal | Shuffle |
|--------|--------------|---------|
| Round creation | All rounds created upfront | First round only, rest created dynamically |
| Pick order | Predetermined | Calculated after each pick |
| Predictable | Yes | No |
| MMR simulation | Can predict final team MMRs | Cannot predict |

### Team total_mmr Calculation

```python
total_mmr = captain.mmr + sum(member.mmr for member in members if member != captain)
```

The captain is always included, and members exclude the captain to avoid double-counting.
