# ScrollArea inside Dialog — clipping contract

Long forms inside `<DialogContent>` MUST scroll via shadcn `<ScrollArea>`, not raw `overflow-y-auto`. The Radix Viewport gives a brand-styled thin scrollbar; the OS-default scrollbar inside an otherwise-themed dialog reads as visual drift.

See [`THEMING-GUIDE.md` §"Dialog Widths"](../../THEMING-GUIDE.md#dialog-widths) for width conventions; this reference covers the **clipping contract** that makes the ScrollArea inside a Dialog actually work.

## The rule

When `<DialogContent>` contains a `<ScrollArea>` (or any flex child that's expected to scroll), `<DialogContent>` MUST carry `overflow-hidden`.

```tsx
// ✓ correct
<DialogContent className="flex max-h-[90vh] flex-col overflow-hidden sm:max-w-2xl">
  <DialogHeader>…</DialogHeader>
  <ScrollArea className="flex-1 min-h-0 -mx-6 px-6">
    <div className="flex flex-col gap-4 pb-4">{/* form body */}</div>
  </ScrollArea>
  <DialogFooter>…</DialogFooter>
</DialogContent>

// ✗ wrong — form grows past the dialog edge, ScrollArea never scrolls
<DialogContent className="flex max-h-[90vh] flex-col sm:max-w-2xl">
  <ScrollArea className="flex-1 min-h-0 -mx-6 px-6">…</ScrollArea>
</DialogContent>
```

Decision dialogs (`ConfirmDialog`, plain `AlertDialog` with two buttons) do NOT need this — their content fits and never overflows. The rule applies only to form-heavy modals with a `<ScrollArea>` child.

## Why

shadcn's default `DialogContent` has no `overflow-hidden`. Without it, the chain unravels:

1. The form (`flex-1`) inside the dialog grows past `max-h-[90vh]` because nothing is clipping it.
2. The `<ScrollArea>` Root with `flex-1 min-h-0` inherits the unconstrained height — it has no definite parent height to bound against.
3. The Radix `<Viewport>` inside uses `height: 100%` (`size-full`). With no definite parent height, that resolves to `auto` (= content height).
4. Radix sees `viewport.scrollHeight === viewport.clientHeight` (no internal overflow), keeps the Viewport's `overflow` at `hidden`, and never enables the scrollbar.
5. Content renders past the dialog's visual edge. Users see broken layout; Playwright reports *"Element is outside of the viewport"* on clicks below the fold.

The Radix Viewport IS the scrolling element (per [radix-ui/primitives scroll-area source](https://github.com/radix-ui/primitives/blob/main/packages/react/scroll-area/src/scroll-area.tsx)) — it sets `overflow: scroll` itself, conditional on detected overflow. Once `<DialogContent>` clips, all the height calculations resolve and Radix enables the scrollbar.

## The `-mx-6 px-6` cancel trick

`<DialogContent>` carries `p-6` (24px padding). A naive `<ScrollArea>` inside that padding renders its scrollbar 24px in from the dialog edge — visible whitespace on the right of the scrollbar that looks unfinished. Cancel the padding on the ScrollArea and re-add it on the inner content wrapper:

```tsx
<ScrollArea className="flex-1 min-h-0 -mx-6 px-6">  {/* cancel-then-readd */}
  <div className="flex flex-col gap-4 pb-4">{/* content lives here */}</div>
</ScrollArea>
```

This sits the scrollbar flush against the dialog's inner edge without chopping content horizontally.

## Severity & review

Form-heavy `<DialogContent>` with a `<ScrollArea>` (or any flex-scroll child) but no `overflow-hidden` is a `block` finding. Symptoms reviewers will see:

- Visual: content rendering past the dialog's visual edge (often only visible at certain viewport sizes).
- Playwright: `Element is outside of the viewport` errors when clicking fields below the fold.
- Bug history: PR #220 fixed exactly this on the `EventSignupModal`.

See [grep-recipes.md §Dialogs](grep-recipes.md#dialogs) for the `rg` recipe that flags this.
