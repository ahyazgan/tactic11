/**
 * Kök rota — giriş sonrası persona launcher.
 *
 * Teknik ekipten biri girince önce rolünü seçer (Analist / TD / Scout /
 * Sportif Direktör), sonra sadece o rolün görev kartlarını görür. Geri kalan
 * tüm ekranlar (Genel Bakış dahil → /overview) kenar menüden erişilebilir.
 *
 * Eski davranış: `/` doğrudan Genel Bakış'ı render ederdi. Artık Genel Bakış
 * "Sportif Direktör" personasının bir görevi olarak /overview'da durur.
 */

import { PersonaLauncher } from "@/components/persona-launcher";

export default function HomePage() {
  return <PersonaLauncher />;
}
