# Severity Rubric

Brand-review findings are graded so reviewers can triage quickly. Use these definitions when emitting findings as part of a `/review` pass.

## Levels

### `block` — Must fix before merge

User-visible affordance is wrong, accessibility is broken, or the brand contract is violated in a load-bearing way.

Examples:
- Primary action wired as raw `<button>` (loses brand gradient, 3D depth, focus ring) — should be `<PrimaryButton>`.
- `<Button onClick={handleSave}>` for a domain action (button policy violation) — should be `<PrimaryButton>` / `<SubmitButton>` / `<ConfirmButton>`.
- Raw `<img>` rendering a user avatar (skips Discord CDN handling, fallback initials, memoization) — must be `<UserAvatar>`.
- Manual breadcrumb `<nav>` on a required detail page — must be `<EntityBreadcrumb>`.
- `<DialogContent className="bg-gradient-to-r ...">` — silently strips `bg-background`.
- `<Dialog>` / `<AlertDialog>` without a Title — fails screen-reader.
- Hardcoded hex / oklch in `className` (`bg-[#7c3aed]`).
- Hand-rolled brand gradient (`from-violet-500 to-blue-500`) — must import `brandGradient` or use `<PrimaryButton>`.
- New shadcn primitive added outside `frontend/app/components/ui/`.
- Color-only status indicator (no text content alongside the colored class).
- Hand-rolled `<AlertDialog>` for a confirm flow (yes/no, positive or negative) outside `components/ui/dialogs/`.
- `window.confirm()` called from any `.tsx`/`.ts` file under `frontend/app/`.
- Hand-rolled `<AlertDialogAction>` / `<AlertDialogCancel>` outside `components/ui/`.
- Hand-rolled name-match destructive input gating a delete (use `<DeleteDialog>` instead).

### `warn` — Should fix, but won't block

Drift from convention; not user-breaking but compounds over time.

Examples:
- Raw `bg-slate-*` on surfaces instead of `bg-base-*`.
- Raw `text-slate-*` / `text-gray-*` instead of `text-foreground` / `text-muted-foreground`.
- Raw `text-green-500` / `text-red-500` for status instead of `text-success` / `text-error`.
- `space-x-*` / `space-y-*` instead of `flex gap-*`.
- Template-literal conditional `className` instead of `cn()`.
- Hand-rolled `shadow-[0_0_...]` instead of `brandGlow` / `shadow-brand-glow`.
- New button file added outside the `buttons/` folder convention (root for generic, `icons/` for icon-only, `<domain>/` for domain-specific).
- `<DestructiveButton>` used inside a dialog (should be `<ConfirmButton variant="destructive">`).

### `nit` — Cosmetic / future cleanup

Style consistency only.

Examples:
- `w-4 h-4` instead of `size-4`.
- Sizing classes on icons inside a brand button wrapper (the wrapper handles it).
- Missing `aria-hidden` on a decorative icon next to existing labeled text.
- Comment narrating WHAT a className does (the className already does that).
- Inconsistent button size choice (`size="sm"` where `size="default"` would match neighbors).

## Output Format

When emitted as part of a review pass, format each finding as one block:

```
brand: <severity> · <file>:<line> — <one-line summary>
  why: <THEMING-GUIDE.md section or component contract>
  fix: <concrete code change, ideally a minimal diff>
```

Examples:

```
brand: block · frontend/app/routes/tournament/$pk.tsx:84 — raw <button> for "Start Tournament" CTA
  why: THEMING-GUIDE.md §"Button Policy" — user-facing actions must use a brand wrapper; raw <button> loses gradient, 3D depth, focus ring
  fix: replace with <PrimaryButton onClick={handleStart}>Start Tournament</PrimaryButton>

brand: block · frontend/app/features/teams/TeamRoster.tsx:42 — raw <img> for team-captain avatar
  why: THEMING-GUIDE.md §"User Avatars" — avatars must use <UserAvatar> for Discord CDN handling and fallbacks
  fix: <UserAvatar user={captain} size="md" border="captain" />

brand: warn · frontend/app/features/draft/DraftPanel.tsx:128 — bg-slate-900 on container
  why: THEMING-GUIDE.md §"Background Scale (Slate)" — surfaces use bg-base-* for semantic elevation
  fix: replace bg-slate-900 with bg-base-900

brand: nit · frontend/app/components/MatchHeader.tsx:18 — w-6 h-6 on icon
  why: shadcn convention — size-* for equal width/height
  fix: replace `w-6 h-6` with `size-6`
```

## Counting & Triage

A diff with **any `block`** is not ready to merge — the reviewer should reply with the list and stop. `warn` and `nit` findings can be batched into a follow-up PR when there are too many to fix in-place.

Common cluster pattern: when a contributor adds a new feature folder, all the `block`s tend to come from the same root cause (e.g. they didn't know about the brand button library). Surface that root cause in the review summary, not just the per-line findings.
