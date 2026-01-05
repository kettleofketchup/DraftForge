# Bracket Visualization Redesign

## Overview

Redesign the tournament bracket visualization to use a single ReactFlow instance with ELK.js layout, supporting configurable elimination types per round and multiple tournament formats.

## Requirements

1. **Single ReactFlow instance** for entire double elimination bracket (not split panels)
2. **Left-to-right ELK.js layout** - bracket aligned to left, flows right
3. **Edges only for winner advancement** - show who continues to next round
4. **Visual differentiation** for losers bracket (horizontal divider + color)
5. **Configurable elimination per round** - single vs double per game
6. **Format presets** - 4-team double elim, swiss, custom

## Backend Changes

### New Game Model Fields

```python
# app/models.py - Game model additions

elimination_type = models.CharField(
    max_length=10,
    choices=[("single", "Single Elimination"), ("double", "Double Elimination")],
    default="double",
    help_text="single=loser out, double=loser drops to losers bracket"
)

loser_next_game = models.ForeignKey(
    "self",
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
    related_name="loser_source_games",
)

loser_next_game_slot = models.CharField(
    max_length=10,
    choices=[("radiant", "Radiant"), ("dire", "Dire")],
    null=True,
    blank=True,
)

# For Swiss format tracking
swiss_record_wins = models.IntegerField(default=0)
swiss_record_losses = models.IntegerField(default=0)
```

### Serializer Updates

Add new fields to `BracketGameSerializer`:
- `elimination_type`
- `loser_next_game`
- `loser_next_game_slot`
- `swiss_record_wins`
- `swiss_record_losses`

### View Updates

Update `advance_winner` in bracket views to also advance loser when `elimination_type='double'`.

## Frontend Changes

### Configuration Schema

```typescript
interface BracketConfig {
  teamCount: number;
  format: 'single_elimination' | 'double_elimination' | 'swiss' | 'custom';
  rounds: RoundConfig[];

  swiss?: {
    roundCount: number;
    winsToAdvance?: number;
    lossesToEliminate?: number;
    tiebreaker: 'buchholz' | 'head_to_head' | 'game_differential';
  };
}

interface RoundConfig {
  id: string;
  bracketType: 'winners' | 'losers' | 'grand_finals' | 'swiss';
  roundNumber: number;
  gameCount: number;
  eliminationType: 'single' | 'double' | 'swiss';
  advancement: AdvancementRule[];
  swissMatching?: 'random' | 'seeded' | 'record_based';
}

interface AdvancementRule {
  outcome: 'winner' | 'loser';
  targetRound: string;
  targetSlot: 'radiant' | 'dire' | 'auto';
}
```

### 4-Team Double Elimination Preset

```typescript
export const FOUR_TEAM_DOUBLE_ELIM: BracketPreset = {
  name: '4-Team Double Elimination',
  teamCount: 4,
  games: [
    // Winners R1 - both games double elim (losers drop)
    { id: 'w-1-0', bracket: 'winners', round: 1, pos: 0, elimType: 'double',
      winnerTo: 'w-2-0', winnerSlot: 'radiant', loserTo: 'l-1-0', loserSlot: 'radiant' },
    { id: 'w-1-1', bracket: 'winners', round: 1, pos: 1, elimType: 'double',
      winnerTo: 'w-2-0', winnerSlot: 'dire', loserTo: 'l-1-0', loserSlot: 'dire' },
    // Winners Final - double elim (loser drops to losers final)
    { id: 'w-2-0', bracket: 'winners', round: 2, pos: 0, elimType: 'double',
      winnerTo: 'gf-1-0', winnerSlot: 'radiant', loserTo: 'l-2-0', loserSlot: 'radiant' },
    // Losers R1 - single elim (loser out)
    { id: 'l-1-0', bracket: 'losers', round: 1, pos: 0, elimType: 'single',
      winnerTo: 'l-2-0', winnerSlot: 'dire' },
    // Losers Final - single elim
    { id: 'l-2-0', bracket: 'losers', round: 2, pos: 0, elimType: 'single',
      winnerTo: 'gf-1-0', winnerSlot: 'dire' },
    // Grand Finals
    { id: 'gf-1-0', bracket: 'grand_finals', round: 1, pos: 0, elimType: 'single' },
  ],
};
```

### BracketView.tsx Rewrite

Key changes:
1. Single `<ReactFlow>` instance containing all matches
2. Use `useElkLayout` hook with `elk.direction: 'RIGHT'`
3. ELK partitioning to keep winners above losers
4. Visual differentiation:
   - Losers nodes: amber/orange background tint via node className
   - Horizontal divider annotation between winners and losers

### Edge Logic

Only create edges when:
1. Match has `winner` set
2. Winning team appears in target match (`next_game`)

```typescript
const edges = matches
  .filter(m => m.winner && m.nextMatchId)
  .filter(m => {
    const target = matchMap.get(m.nextMatchId);
    const winningTeam = m.winner === 'radiant' ? m.radiantTeam : m.direTeam;
    return target?.radiantTeam?.pk === winningTeam?.pk ||
           target?.direTeam?.pk === winningTeam?.pk;
  })
  .map(m => ({
    id: `${m.id}-${m.nextMatchId}`,
    source: m.id,
    target: m.nextMatchId,
    type: 'bracket',
  }));
```

### Node Styling

```typescript
// In MatchNode.tsx
const bgClass = data.bracketType === 'losers'
  ? 'bg-amber-950/30 border-amber-700/50'
  : data.bracketType === 'grand_finals'
  ? 'bg-purple-950/30 border-purple-700/50'
  : 'bg-background';
```

## 4-Team Bracket Structure

```
Round 1 (2 games):     Round 2:              Finals:
┌─────────┐
│ W-R1-G1 │──winner──┐
└─────────┘          │  ┌─────────┐
     │               ├─▶│ W-Final │──winner──┐
     │loser          │  └─────────┘          │   ┌─────────┐
     │               │       │loser          ├──▶│Grand F. │
     │  ┌─────────┐  │       │               │   └─────────┘
     │  │ W-R1-G2 │──┘       │               │
     │  └─────────┘          │               │
     │       │loser          ▼               │
     │       │          ┌─────────┐          │
     └──────▶│─────────▶│ L-Final │──winner──┘
             │          └─────────┘
             ▼
        ┌─────────┐
        │ L-R1    │──winner──┘
        └─────────┘
```

## Testing

Use tournament 2 for bracket generation testing:
1. Generate 4-team double elimination bracket
2. Verify ELK layout renders left-to-right
3. Verify losers bracket has amber styling
4. Verify edges only appear for completed matches with winners
5. Test Chrome MCP visual inspection

## Migration Steps

1. Add new fields to Game model
2. Run migrations
3. Update serializers
4. Update bracket views
5. Create frontend presets
6. Rewrite BracketView.tsx
7. Test with tournament 2
