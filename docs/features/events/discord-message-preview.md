# Discord Message Preview

Every Discord message an event can post or DM has a **Preview** button next to its toggle on the event form's Discord tab. The preview shows exactly what Discord will receive, built from the values currently in the form, saved or not. Opening a preview never sends anything and never saves the form.

## Where the buttons are

Open the Discord tab in any of these forms:

| Form | What the preview is built from |
|------|--------------------------------|
| Edit event | The saved event with your unsaved edits applied |
| Create event (single) | An unsaved event built from the form |
| Create event (recurring) | The first event the new series would create |
| Add extra session to a series | The one-off event that would be created |
| Edit series | The series' next upcoming event, or the next one it would create, with your edits applied |
| Organization event defaults | No preview (see [Organization defaults](#organization-defaults)) |

The Preview button works whether the toggle is on or off, so you can check a message before turning it on. With the toggle off, the dialog's first line says nothing will be sent.

## What each preview shows

| Toggle | Preview | Where it goes |
|--------|---------|---------------|
| Create Discord scheduled event | The scheduled event card: name, description, start and end time, location | The server's Events tab |
| Synchronize signups | The scheduled event card as Discord will hold it after the sync: the name and times it was created with, and the description with the signup counts. Syncing changes only the description, so edits to the title or time do not reach an existing scheduled event | The server's Events tab |
| Send signup reminder (series only) | The DM sent to subscribers | A direct message to each series subscriber who has not signed up |
| Profile update reminder | The reminder asking signed-up members to complete their profile | The announcement channel |
| Post attendance reminder in Discord | The attendance reminder | The announcement channel |
| Mention signed-up members before start | The reply that mentions everyone signed up, split into several messages when the list is long | A reply to the signup post |
| Post event signup embed | The signup post, with its buttons | A new thread in the signup channel (or the channel itself), falling back to the announcement channel |
| Pre-day announcement | The announcement, or the signup post if that is what this configuration posts instead. Before the signup post exists, the "Sign up here!" link points to the signup channel in place of the post | The announcement channel |
| Post new events (series only) | The post announcing a newly created event | The announcement channel |

*Mark signups as interested* has no preview because it sends no message, and the announcement channel picker is a setting rather than a message.

Role and channel mentions show their names when DraftForge can read them from your Discord server; otherwise they show as `@role:1234…` or `#channel:1234…`. Times written as Discord timestamps show in your own time zone, as Discord shows them to each reader.

## "Not sent" lines

Above the message the dialog says whether the message would be sent, and if not, why. Common reasons:

- **Off**: the toggle is off.
- **No channel selected**: the announcement or signup channel is empty.
- **No Discord server linked**: the organization has no Discord server.
- **Not sent yet: this posts when signups open**: the signup post and pre-day announcement are only posted when signups open. The preview shows them as they will look at that moment, not as they would look now.
- **Not sent now: only while signups are open or during roll call**: the start mention.
- **The signup post has not been posted yet**: the start mention replies to the signup post, so it needs one.
- **The event start time has passed**, **the series is paused** or **the series has ended**.
- **No one would be mentioned right now**: the start mention has nobody to mention. The dialog still shows the header it would use.

Notes under the message explain behaviour that is easy to miss. For example, later signup changes edit the signup post's embed and buttons but never its role mentions, and syncing signups replaces the scheduled event's description with the event description.

## Unsaved events and series

When the event is not saved yet, a banner says so. Links to the event page point to the events list until the event exists. If a required field is empty (such as the date and time, or a series' schedule), the dialog lists the fields to fill in instead of showing a message.

For a series, the preview follows what saving would do. If you change the schedule, the preview uses the event that matches the new schedule. If the series is paused or ended, its existing upcoming event still posts, and the dialog says so.

## Organization defaults

The organization's event defaults form has Preview buttons, but they open a short note instead of a message. Defaults are not an event, so a preview has no date, signups or channels to build from. Create or edit an event that uses the defaults to see its messages.

## Example

```
┌ Preview: Signup post ─────────────────────────────────────── ✕ ┐
│ Posts in #event-signups as a new thread "Friday Inhouse".       │
│ If that fails, posts in #announcements without role mentions.   │
│ Not sent yet: this posts when signups open.                     │
│ ┌──────────────────────────────────────────────────────────────┐│
│ │ DraftForge  APP                                              ││
│ │ @Inhouse Pings                                               ││
│ │ ▌ Friday Inhouse                                             ││
│ │ ▌ Weekly 5v5 inhouse. Bring a mic.                           ││
│ │ ▌ When            Max Players     Event Page                 ││
│ │ ▌ Fri, Dec 4 6PM  10              View                       ││
│ │ [ Sign Up ] [ Tentative ] [ Decline ]                        ││
│ └──────────────────────────────────────────────────────────────┘│
│ Later signup changes update this post's embed and buttons only.│
│                                                       [ Close ] │
└─────────────────────────────────────────────────────────────────┘
```

## For developers

The preview is rendered on the server by the same functions the Celery tasks use to build the real message, so a preview cannot drift from what is sent.

- **Never write Discord message text in TypeScript.** The frontend only renders the payload the backend returns. If a builder in `backend/events/discord/embeds.py` or `backend/events/start_mention.py` needs data the preview cannot give it, change the builder so the task and the preview both pass it in (as with the `signups=` argument).
- **Endpoint:** `POST /api/events/discord-preview/` with `{kind, context, values}`. It is staff-only, using the same permission as editing the event, and it never sends, saves or calls the internal API. `backend/events/discord/preview.py` builds an in-memory event from `context` and `values`.
- **Send conditions** live in `backend/events/discord/gates.py`. The tasks and the preview both call them, so a "not sent" reason in the dialog is the condition the task checks.
- **Reusable UI:** `frontend/app/components/discord/` has `DiscordMessagePreview` (content, embeds, buttons, selects and Components V2), `DiscordScheduledEventCard` and `DiscordPreviewButton` (a button that opens a dialog and calls a `fetchPreview` you pass it). They know nothing about events; the promotion compose panel uses the same renderer.

### Adding a preview kind

1. Make the task build its payload through a pure builder, with a characterization test pinning the current payload before the refactor.
2. Add or reuse a gate in `events/discord/gates.py` and call it from the task.
3. Add the kind to `PreviewKind` in `events/discord/preview_schema.py` and its builder to `KIND_BUILDERS` in `events/discord/preview.py`, with a test that the preview equals what the task sends.
4. Regenerate the Zod schemas with `just py::gen-discord-preview` (CI checks them with `--check`).
5. Add the kind's title to the static lookup in `features/event-discord-preview/EventDiscordPreviewButton.tsx` and any new gate or note code to `EventPreviewBody.tsx`, with `en` and `es` strings in `discordPreview.json`.
6. Put an `EventDiscordPreviewButton` in the toggle's row in `DiscordConfigSection.tsx` (test id `discord-preview-<kind>`).
