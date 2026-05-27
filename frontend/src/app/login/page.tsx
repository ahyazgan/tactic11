"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login, setTokens } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenantSlug, setTenantSlug] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const pair = await login(email, password, tenantSlug || undefined);
      setTokens(pair.access_token, pair.refresh_token);
      router.push("/matches");
    } catch (e) {
      setError(e instanceof Error ? e.message : "login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-8">
      <form onSubmit={onSubmit} className="card w-full max-w-sm space-y-4">
        <h1 className="text-xl font-bold">Giriş</h1>
        <input
          type="email" placeholder="email"
          required value={email} onChange={(e) => setEmail(e.target.value)}
          className="w-full bg-bg border border-border rounded px-3 py-2"
        />
        <input
          type="password" placeholder="şifre"
          required value={password} onChange={(e) => setPassword(e.target.value)}
          className="w-full bg-bg border border-border rounded px-3 py-2"
        />
        <input
          placeholder="tenant slug (opsiyonel)"
          value={tenantSlug} onChange={(e) => setTenantSlug(e.target.value)}
          className="w-full bg-bg border border-border rounded px-3 py-2"
        />
        {error && <p className="text-bad text-sm">{error}</p>}
        <button
          type="submit" disabled={loading}
          className="w-full bg-accent text-white font-semibold rounded px-4 py-2 disabled:opacity-50"
        >
          {loading ? "..." : "Giriş yap"}
        </button>
      </form>
    </main>
  );
}
