- Self-set Steam Friend IDs are checked against Steam: an ID that belongs to no Steam
  account is refused on the profile page, web and Discord signups and the org Dota
  profile (#790). If Steam is unreachable the ID is saved and marked "Not checked
  against Steam".
- Staff see an Unverified or Verified badge next to a member's Friend ID in the MMR
  approval dialog, the player modal and the tournament Players tab, with Steam and
  Dotabuff links and a Verify action. Verified IDs show which organization vouched.
- Site staff can verify any member; event and league staff can verify members who signed
  up to their event themselves. Members see "Unverified" on their own profile.
- New endpoint `GET/POST /api/users/<id>/steam-verification/`.
- New docs page: Steam Friend ID verification.
