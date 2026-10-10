"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { login, setTokens } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [tenant, setTenant] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (DEMO_MODE) router.replace("/");
  }, [router]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const pair = await login(email.trim(), password, tenant.trim() || undefined);
      setTokens(pair.access_token, pair.refresh_token);
      const requested = new URLSearchParams(window.location.search).get("next") || "/";
      let next = "/";
      try {
        const destination = new URL(requested, window.location.origin);
        // A login link may return to this app, never to a third-party URL.
        if (destination.origin === window.location.origin && destination.pathname !== "/login") {
          next = destination.pathname + destination.search + destination.hash;
        }
      } catch { /* A malformed return address falls back to the home page. */ }
      window.location.assign(next);
    } catch {
      setError("Giriş yapılamadı. E-posta, parola ve kulüp kodunu kontrol edip tekrar deneyin.");
      setBusy(false);
    }
  }

  if (DEMO_MODE) {
    return <main className="min-h-screen flex items-center justify-center p-8"><p>Yönlendiriliyor…</p></main>;
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-8">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl border p-6" style={{ background: "var(--panel)", borderColor: "var(--line)" }}>
        <h1 className="text-xl font-bold">Manager’a giriş</h1>
        <p className="text-sm" style={{ color: "var(--muted)" }}>Video işlemek ve kulübünüze ait işlemleri yönetmek için hesabınızla giriş yapın.</p>
        <label className="block text-sm">E-posta
          <input className="mt-1 block w-full rounded-sm border p-2" type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} disabled={busy} />
        </label>
        <label className="block text-sm">Parola
          <input className="mt-1 block w-full rounded-sm border p-2" type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} disabled={busy} />
        </label>
        <label className="block text-sm">Kulüp kodu (isteğe bağlı)
          <input className="mt-1 block w-full rounded-sm border p-2" autoComplete="organization" value={tenant} onChange={e => setTenant(e.target.value)} disabled={busy} />
        </label>
        {error && <p role="alert" className="text-sm" style={{ color: "var(--crit)" }}>{error}</p>}
        <button className="w-full rounded-sm p-2 font-semibold" type="submit" disabled={busy} style={{ background: "var(--accent)", color: "#fff" }}>{busy ? "Giriş yapılıyor…" : "Giriş yap"}</button>
      </form>
    </main>
  );
}
