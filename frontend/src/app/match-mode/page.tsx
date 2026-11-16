/**
 * Eski adres — içerik Maç Günü ekranının ilgili aşamasına taşındı.
 */

import { redirect } from "next/navigation";

export default function MatchModeRedirect() {
  redirect("/match-day?asama=canli");
}
