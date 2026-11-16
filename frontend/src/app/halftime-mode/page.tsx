/**
 * Eski adres — içerik Maç Günü ekranının ilgili aşamasına taşındı.
 */

import { redirect } from "next/navigation";

export default function HalftimeModeRedirect() {
  redirect("/match-day?asama=devre");
}
