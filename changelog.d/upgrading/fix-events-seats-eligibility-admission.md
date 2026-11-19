Starting roll call now removes approved but unconfirmed players who are not on a team from the tournament roster on every event, whatever its sign-up settings. Before this release they were only removed at tournament start.

Before deploying, count the events, series and org defaults that have a non-default sign-up rule. Run this read-only command from `/app/backend` in the backend container on the production host:

```
python manage.py shell -c "from events.models import Event, EventRepeater, OrgEventDefaults as D; from events.constants import EventState as S; from django.db.models import Q; q=Q(allow_user_signups=False)|Q(roll_call_enabled=True); live=[S.UPCOMING, S.SIGNUPS_OPEN, S.ROLL_CALL]; print({'Event': Event.objects.filter(q, state__in=live).count(), 'EventRepeater': EventRepeater.objects.filter(q).count(), 'OrgEventDefaults': D.objects.filter(q).count()})"
```

It prints one count per model, for example `{'Event': 0, 'EventRepeater': 0, 'OrgEventDefaults': 0}`. The Event count covers only upcoming, signups-open and roll-call events, because the settings no longer affect finished ones. All zeros means no live event, series or org default has a non-default sign-up rule. A non-zero Event count means those events behave differently once this release is live. Where "Members can sign themselves up" is off, self sign-ups on the web and through Discord buttons and reactions are refused (organizers can still add players). Where "Mandatory RSVP Confirmation" (Ready check tab) is on, approved players stay off the tournament roster during signups: the roster self-heal and the resync after changing the setting leave them off, and reopening signups does not put them back. Series and org-default rows do not change anything themselves; they pass the setting on to events created from them. Review those rows with their organizers, and change either setting in the event, series or org-defaults form if the new behaviour is not wanted.

This release has two migrations, both applied by the normal migrate step. `events.0025_eventsignup_unmet_requirements` adds `unmet_requirements` to signups (empty for existing rows; it fills in the next time a signup is checked) so staff can see why a signup is held. `org.0011_playerdotaprofile_rank_declared_at` adds `rank_declared_at` to Dota profiles and, in a data step, stamps it on every profile that already shows a rank choice (a rank status other than "never", a rank or Battle Cup screenshot, a rank medal or a Battle Cup tier). Profiles left unstamped count as undeclared, so on auto-approve events with Dota rank gates those players are held for approval (`dota_rank_undeclared`) until they pick a rank status.

After deploying, run the waitlist rebalance once from `/app/backend` in the backend container. Tentative signups no longer hold seats, so open events can have free seats with players still on the waitlist. Preview first; the dry run changes nothing, prints a line for each event that has players to promote, then a total (`Would promote N signup(s).`):

```
python manage.py rebalance_event_waitlists --dry-run
python manage.py rebalance_event_waitlists
```

The second command promotes waitlisted players into those seats on events with signups open and a player cap, refreshes their Discord signup posts and prints the total. It is idempotent, so running it again promotes nobody new.
