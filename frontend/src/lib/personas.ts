/**
 * Persona launcher konfigürasyonu.
 *
 * Fikir: teknik ekipten biri giriş yapınca 61 menüyle boğulmasın. Önce
 * "ben kimim / neyle ilgileniyorum" diye bir persona seçsin, sonra SADECE
 * o işin 4-5 görev kartı karşısına çıksın. Geri kalan her şey gizli kalır
 * (silinmez — sidebar/derin linkler hâlâ çalışır, sadece varsayılan görünüm
 * sade olur).
 *
 * Bu dosya tek karar noktasıdır: hangi persona hangi görevleri görür?
 * Görev eklemek/çıkarmak = buradaki listeyi düzenlemek. Kod değişmez.
 */

import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BarChart3,
  CalendarClock,
  ClipboardList,
  FileText,
  GitCompare,
  LineChart,
  MessageSquare,
  Search,
  ShieldHalf,
  Sparkles,
  Target,
  Timer,
  Trophy,
  Users,
} from "lucide-react";

export interface PersonaTask {
  label: string;
  description: string;
  href: string;
  icon: LucideIcon;
}

export interface Persona {
  id: string;
  title: string;
  tagline: string;
  icon: LucideIcon;
  /** Bu persona için varsayılan açılış görevi (en sık yapılan iş). */
  primary: string;
  tasks: PersonaTask[];
}

export const PERSONAS: Persona[] = [
  {
    id: "analyst",
    title: "Analiz Şefi / Analist",
    tagline: "Rakibi çöz, maç önü brief'i hazırla",
    icon: BarChart3,
    primary: "/opponent",
    tasks: [
      { label: "Rakip Analizi", description: "Sıradaki rakibin güçlü/zayıf yönleri, taktik DNA", href: "/opponent", icon: Search },
      { label: "Maç Önü Brief", description: "Veri-kalibre 200 kelimelik maç önü özeti", href: "/prematch-mode", icon: FileText },
      { label: "xG Analizi", description: "Beklenen gol — şut kalitesi ve üretim", href: "/xg", icon: Target },
      { label: "Taktik Profil", description: "Takım kimliği: pres, dikine oyun, alan kullanımı", href: "/tactical-real", icon: LineChart },
      { label: "Haftalık Rapor", description: "Haftanın özeti — form, trend, öne çıkanlar", href: "/weekly-report", icon: CalendarClock },
    ],
  },
  {
    id: "coach",
    title: "Teknik Direktör",
    tagline: "Maça nasıl çıkalım — karar, tek ekran",
    icon: ClipboardList,
    primary: "/match-plan",
    tasks: [
      { label: "Maç Planı", description: "Önerilen ilk 11 + kurgu, tek bakışta", href: "/match-plan", icon: ClipboardList },
      { label: "Maç Modu", description: "Maç-içi canlı karar desteği", href: "/match-mode", icon: Activity },
      { label: "Devre Arası", description: "İlk yarı analizi + ikinci yarı ayarı", href: "/halftime-mode", icon: Timer },
      { label: "Yardımcı Manager", description: "Doğal dil sor: 'Fener maçına nasıl çıkalım?'", href: "/chat", icon: MessageSquare },
    ],
  },
  {
    id: "scout",
    title: "Scout / Altyapı",
    tagline: "Oyuncu izle, benzerini bul, raporla",
    icon: Search,
    primary: "/scout",
    tasks: [
      { label: "İzleme Listesi", description: "Takip ettiğin oyuncular + otomatik uyarılar", href: "/scout", icon: Users },
      { label: "Scout Raporları", description: "Oyuncu değerlendirme ve scout notları", href: "/scout-reports", icon: FileText },
      { label: "Kadro / Oyuncu", description: "Oyuncu profilleri ve karşılaştırma", href: "/squad", icon: GitCompare },
      { label: "Transfer", description: "Transfer hedefleri ve uygunluk", href: "/transfer", icon: Sparkles },
    ],
  },
  {
    id: "director",
    title: "Sportif Direktör / Yönetim",
    tagline: "Üst seviye özet ve karar isabeti",
    icon: Trophy,
    primary: "/overview",
    tasks: [
      { label: "Genel Bakış", description: "Kulüp panosu — sıradaki maç, riskler, görevler", href: "/overview", icon: ShieldHalf },
      { label: "TD Performansı", description: "Teknik direktör performansı veriyle ölçülü", href: "/manager-performance", icon: BarChart3 },
      { label: "Karar Takip", description: "Verilen kararların gerçek isabet oranı", href: "/decisions/track", icon: Target },
      { label: "Kalibrasyon", description: "Tahmin doğruluğu — Brier / log-loss / ECE", href: "/calibration", icon: LineChart },
      { label: "Sözleşmeler", description: "Oyuncu sözleşme durumu ve takvimi", href: "/contracts", icon: CalendarClock },
    ],
  },
];

const STORAGE_KEY = "tactic11_persona";

export function getStoredPersona(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(STORAGE_KEY);
}

export function storePersona(id: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, id);
}

export function clearStoredPersona(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
}

export function findPersona(id: string | null): Persona | undefined {
  if (!id) return undefined;
  return PERSONAS.find((p) => p.id === id);
}
