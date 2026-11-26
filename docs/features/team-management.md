# Managing a Team

Tournament staff change a team's roster from the team manage dialog. Open a team from the
tournament page and choose **Manage team**. Only tournament staff see it: site staff, the
league's admins and staff, and the organization's owner, admins and staff.

Every change asks for a reason. It is saved as one row on the dialog's **History** tab,
along with the roster before and after the change.

## Actions

The roster table lists members, stand-ins and dropouts. Each row's menu has the actions
that apply to that player:

| Action | What it does |
|--------|--------------|
| Make captain | Makes a member or stand-in the captain. |
| Make deputy / Clear deputy | Sets or clears the deputy captain. |
| Mark dropout | Moves a member to the dropouts. If they were captain, the deputy becomes captain; with no deputy, the remaining member with the highest MMR does. |
| Restore | Brings a dropout back as a member. |
| Add stand-in | Adds a player from the tournament or organization as a stand-in. |
| Sub in | Swaps a stand-in in for a member. |
| Remove stand-in | Takes a stand-in off the team. |
| Replace captain | Makes any eligible player captain in one step (below). |

You can also rename the team from the dialog.

If you change the captain while a team draft or hero draft is running, the draft moves
to the new captain.

## Replace captain

Use **Replace captain** when a captain leaves and someone else takes over, including a
captain from a team that is already out of the tournament. You can open it from the
**Replace captain** button in the toolbar, or from the **Replace captain…** item in the
captain row's menu.

The picker shows:

- **This team**: the team's members, stand-ins and dropouts.
- **Free players (eliminated teams)**: players whose team is out of the tournament,
  labelled with that team and its placement, for example `TM Delta · Eliminated · 4th`.
- Search results for anyone else in the tournament or organization.

Players on a team that is still in the tournament are shown as `On <team>` and can't be
picked.

When you confirm, in one audited step:

1. The new captain becomes a member of the team. If they were a stand-in or a dropout,
   they are moved to members, and they are added to the tournament's players if they
   weren't already one.
2. If they were the deputy, the deputy is cleared.
3. They become captain.
4. The old captain is marked as a dropout. To keep them on the team as a member, untick
   **Mark <name> as a dropout (they left the team)**.

Replace captain never removes the last member of the team, and you can repeat it. A
captain who came from another team can be replaced the same way later.

!!! tip "Mark dropout versus Replace captain"

    **Mark dropout** (or **Sub in** replacing the captain) promotes the deputy, or the
    highest-MMR member when there is no deputy. The confirmation names who that will be.
    Use Replace captain when you want to pick the new captain yourself.

If the new captain doesn't meet the event's signup requirements, the dialog asks you to
confirm the [staff override](../development/staff-overrides.md) before it saves.

## In tournament, Eliminated or Winner

A badge next to the dialog title shows the team's status:

| Badge | Meaning |
|-------|---------|
| In tournament | The team has no placement yet. |
| Eliminated · 4th | The team is out, and finished in that place. |
| Winner | The team won the tournament (placement 1). |

The status comes from the team's **placement**, which the bracket sets when a team is
knocked out.

## Players of eliminated teams

A player can only be on one team that is still in the tournament. Once a team has a
placement, its players are free: you can add them as a stand-in, restore them, or make
them captain on another team.

The eliminated team is not changed. Its roster, captain, placement and leadership
records stay as they were, so the player is listed on both teams.

!!! warning "The bracket doesn't always set placement"

    Placement is set automatically only for **double elimination** brackets where results
    are entered from the bracket view. In these cases it is not set, and the team's
    players still count as busy:

    - single elimination brackets;
    - swiss brackets;
    - results linked automatically from Steam;
    - results saved with the bracket toolbar's **Save** button.

    If you try to add one of their players to another team, the refusal names their team
    and tells you to set its placement first. Use **Set placement** (below).

## Set placement

**Set placement** in the dialog header sets the team's final placement (a whole number,
1 or more) or clears it with **Clear (back in tournament)**. Use it to mark a team
eliminated when the bracket didn't, or to fix a wrong placement.

Before it saves, a confirmation step names the team and what happens. Marking a team
eliminated frees its players to join other teams. Every placement change needs a reason
and appears in the team's **History** tab as **Set placement**.

Clearing a placement is refused if one of the team's players has since joined another
team that is still in the tournament. Otherwise that player would be on two live teams.
Undoing a bracket result that would reopen such a team is refused for the same reason.
Move the player back first, then clear the placement.

## Known limitations

- **Leadership.** At the end of an event, a captain's leadership record (captain points,
  teammate ratings, placement award) is saved once, on the team they captained from the
  start. A team taken over by a captain from another team gets no leadership record for
  that event.
