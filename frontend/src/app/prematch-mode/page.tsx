/**
 * Eski adres — içerik Maç Günü ekranının ilgili aşamasına taşındı.
 */

import { redirect } from "next/navigation";

export default function PrematchModeRedirect() {
  redirect("/match-day?asama=hazirlik");
}
