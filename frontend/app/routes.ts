import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
    index("routes/home.tsx"),
    route("tournament", "routes/tournament.tsx"),
    route("about", "routes/about.tsx"),
    route("blog", "routes/blog.tsx")


] satisfies RouteConfig;
