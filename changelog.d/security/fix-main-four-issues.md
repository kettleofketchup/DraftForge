- Creating a team now needs edit access to its tournament. Any logged-in user could
  create a team in any tournament through `POST /api/teams/`, while
  `POST /api/team/register` refused org and league staff (#739).
