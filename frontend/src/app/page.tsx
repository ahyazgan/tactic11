/**
 * Kök rota — açılışta doğrudan Genel Bakış konsolunu gösterir.
 * (Redirect yerine doğrudan render: `/` 200 döner; CI healthcheck'i ve
 * derin linkler sorunsuz çalışır. Eski kart launcher kaldırıldı.)
 */

import OverviewConsolePage from "./overview/page";

export default function HomePage() {
  return <OverviewConsolePage />;
}
