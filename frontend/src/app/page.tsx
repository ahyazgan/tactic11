/**
 * Kök rota — açılışta doğrudan Genel Bakış konsoluna yönlendirir.
 * (Eski kart launcher kaldırıldı; uygulama Genel Bakış ile açılır.)
 */

import { redirect } from "next/navigation";

export default function HomePage() {
  redirect("/overview");
}
