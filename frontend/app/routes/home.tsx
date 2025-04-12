import type { Route } from "./+types/home";
import { Welcome } from "../pages/welcome/welcome";
import { Tournament } from "../pages/tournament/tournament";

export function meta({}: Route.MetaArgs) {
  return [
    { title: "DTX" },
    { name: "description", content: "DTX" },
  ];
}

export default function Home() {
  return <Welcome />;
}
