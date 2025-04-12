import type { Route } from "./+types/home";
import { About } from "../pages/about/about";

export function meta({}: Route.MetaArgs) {
  return [
    { title: "DTX About Us" },
    { name: "description", content: "About us!" },
  ];
}

export default function Home() {
  return <About />;
}
