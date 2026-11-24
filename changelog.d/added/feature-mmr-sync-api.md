- MMR sync API: org admins create personal app tokens (Org Settings → API access) that an
  external service uses to push member MMRs in bulk, matched by Steam ID (32- or 64-bit) or
  Discord ID. A site admin turns it on per org with the new "MMR sync API" locked feature.
  Each token is limited per minute and per day (60/min and 5,000/day by default; site admins
  can override per org), and requests are counted per user per day.
