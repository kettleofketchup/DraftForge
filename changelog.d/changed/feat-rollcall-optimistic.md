- Roll call: confirming, approving, removing or restoring a player now updates their row
  straight away instead of waiting for the server, and the next player can be confirmed while
  earlier requests are still in flight. A small spinner marks rows still saving; if the server
  refuses, the row snaps back and a toast names the player. The event page's signup actions
  update rows the same way and refetch once, after the last action finishes.
