import { type RouteConfig, index, route } from '@react-router/dev/routes';

export default [
  index('routes/home.tsx'),
  route('tournaments', 'routes/tournaments.tsx'),
  route('tournament/:pk/*', 'routes/tournament.tsx'),
  route('organizations', 'routes/organizations.tsx'),
  route('organizations/:organizationId', 'routes/organization.tsx'),
  route('leagues', 'routes/leagues.tsx'),
  route('leagues/:leagueId/:tab?', 'routes/league.tsx'),
  route('about', 'routes/about.tsx'),
  route('blog', 'routes/blog.tsx'),
  route('users', 'routes/users.tsx'),
  route('user/:pk', 'routes/user.tsx'),
  route('logout', 'routes/logoutRedirect.tsx'),
  route('done', 'routes/doneRedirect.tsx'),
  route('profile', 'routes/profile.tsx'),
] satisfies RouteConfig;
