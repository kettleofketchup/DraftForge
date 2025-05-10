import React, { useEffect, useState } from "react";
import TournamentCard from "~/components/tournament/TournamentCard";
import type { TournamentType } from "~/components/tournament/types";
import { getTournaments } from "~/components/api/api";

export const TournamentPage: React.FC = () => {
  const [tournaments, setTournaments] = useState<TournamentType[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchTournaments = async () => {
      try {
        const data = await getTournaments();
        setTournaments(data);
      } catch (error) {
        console.error("Failed to fetch tournaments:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchTournaments();
  }, []);

  if (loading) {
    return <div className="flex justify-center">Loading...</div>;
  }

  return (
    <div className="flex flex-wrap gap-4 justify-center p-4">
      {tournaments.map((tournament) => (
        <TournamentCard key={tournament.pk} tournament={tournament} />
      ))}
    </div>
  );
};

export default TournamentPage;
