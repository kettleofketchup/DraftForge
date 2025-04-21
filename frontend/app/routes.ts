import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
    index("routes/home.tsx"),
    route("tournament", "routes/tournament.tsx"),
    route("about", "routes/about.tsx"),
    route("blog", "routes/blog.tsx"),
    route("done", "routes/login.tsx"),
    route("users", "routes/users.tsx")


] satisfies RouteConfig;
