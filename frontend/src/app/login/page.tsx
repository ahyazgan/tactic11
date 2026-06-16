"use client";

/**
 * Login devre dışı (önizleme modu) — backend deploy edilmediği için giriş
 * akışı kaldırıldı. Bu rotaya gelen herkes doğrudan ana sayfaya (dashboard)
 * yönlendirilir. Backend bağlandığında gerçek login formu geri eklenebilir.
 */

import * as React from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  React.useEffect(() => {
    router.replace("/");
  }, [router]);
  return (
    <main className="min-h-screen flex items-center justify-center p-8">
      <p className="text-textmut text-sm">Yönlendiriliyor…</p>
    </main>
  );
}
