import type { Route } from "./+types/home";
import { Blog } from "../pages/blog/blog";

export function meta({}: Route.MetaArgs) {
  return [
    { title: "DTX: Blog" },
    { name: "description", content: "Welcome to React Router!" },
  ];
}

export default function Home() {
  return <Blog />;
}
