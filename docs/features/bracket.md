# Tournament Brackets

The bracket system provides flexible tournament structure options for organizing competitive matches. Multiple formats are supported to accommodate different tournament sizes and styles.

## Bracket Formats

### Single Elimination

Traditional knockout format where one loss eliminates a team.

**Structure:**
```
Round 1          Quarterfinals    Semifinals       Finals
Team 1 ─┐
        ├─ Winner ─┐
Team 8 ─┘          │
                   ├─ Winner ─┐
Team 4 ─┐          │          │
        ├─ Winner ─┘          │
Team 5 ─┘                     ├─ Champion
                              │
Team 3 ─┐                     │
        ├─ Winner ─┐          │
Team 6 ─┘          │          │
                   ├─ Winner ─┘
Team 2 ─┐          │
        ├─ Winner ─┘
Team 7 ─┘
```

**Characteristics:**

- Fast tournament completion
- High stakes per match
- Clear winner determination
- Best for larger team counts

### Double Elimination

Teams must lose twice to be eliminated, featuring upper and lower brackets.

**Structure:**

- **Upper Bracket**: Winners continue; losers drop to lower bracket
- **Lower Bracket**: One more loss means elimination
- **Grand Finals**: Upper bracket winner vs lower bracket winner

**Characteristics:**

- More forgiving - teams get a second chance
- Longer tournament duration
- More matches for spectators
- True skill determination

### Round Robin

Every team plays against every other team.

**Structure:**
```
         Team A  Team B  Team C  Team D
Team A     -      W       L       W
Team B     L      -       W       W
Team C     W      L       -       L
Team D     L      L       W       -
```

**Characteristics:**

- All teams play equal number of matches
- Points-based standings
- Best for league-style play
- Can feed into playoff brackets

## Bracket Visualization

![Bracket View](../assets/site_snapshots/bracket.png)

<!-- TODO: Add animated bracket demo GIF -->

## Features

### Automatic Bracket Generation

- Seeding based on team rankings or random assignment
- Bye handling for non-power-of-2 team counts
- Automatic match scheduling

### Match Management

- Score reporting by admins or team captains
- Match status tracking (pending, in-progress, completed)
- Winner advancement to next round

### Live Updates

- Real-time bracket updates via WebSocket
- Spectator view for tournament followers
- Match result notifications

## Data Models

### Bracket

| Field | Type | Description |
|-------|------|-------------|
| `tournament` | ForeignKey | Associated tournament |
| `bracket_type` | CharField | `single`, `double`, or `round_robin` |
| `created_at` | DateTime | When bracket was generated |

### Match

| Field | Type | Description |
|-------|------|-------------|
| `bracket` | ForeignKey | Parent bracket |
| `round` | Integer | Round number (1, 2, 3...) |
| `match_number` | Integer | Match position in round |
| `team1` | ForeignKey | First team (null for bye) |
| `team2` | ForeignKey | Second team (null for bye) |
| `winner` | ForeignKey | Winning team (null until complete) |
| `team1_score` | Integer | Team 1's score |
| `team2_score` | Integer | Team 2's score |
| `status` | CharField | `pending`, `in_progress`, `completed` |

## API Endpoints

### Generate Bracket

```
POST /api/tournaments/{id}/bracket/generate/
```

**Request:**
```json
{
  "bracket_type": "single",
  "seeding": "ranked"
}
```

### Report Match Result

```
POST /api/matches/{id}/report/
```

**Request:**
```json
{
  "team1_score": 2,
  "team2_score": 1
}
```

### Get Bracket State

```
GET /api/tournaments/{id}/bracket/
```

**Response:**
```json
{
  "bracket_type": "single",
  "rounds": [
    {
      "round_number": 1,
      "matches": [
        {
          "id": 1,
          "team1": {"id": 1, "name": "Alpha"},
          "team2": {"id": 8, "name": "Omega"},
          "winner": null,
          "status": "pending"
        }
      ]
    }
  ]
}
```

## Frontend Components

### BracketView

Interactive bracket visualization:

- Zoomable and pannable bracket display
- Click matches for details
- Real-time updates
- Mobile-responsive layout

### MatchCard

Individual match display:

- Team names and logos
- Score display
- Match status indicator
- Report result button (for admins)

## Implementation Notes

### Seeding Options

| Option | Description |
|--------|-------------|
| `ranked` | Teams ordered by rating/seed |
| `random` | Random bracket placement |
| `manual` | Admin assigns positions |

### Bye Handling

When team count isn't a power of 2:

1. Calculate byes needed: `next_power_of_2 - team_count`
2. Assign byes to top seeds
3. Bye teams advance automatically to round 2
