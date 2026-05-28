/**
 * Auth helpers — /auth/me ile rol çek, RequireRole HOC.
 * Faz 3'te real refresh interception eklenecek.
 */
"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { apiFetch, clearTokens, getAccessToken } from "./api";

export interface CurrentUser {
  email: string;
  tenant_id?: string;
  tenant_slug?: string;
  role: "admin" | "analyst" | "coach" | "viewer";
}

export function useCurrentUser() {
  const { data, error, isLoading, mutate } = useSWR<CurrentUser>(
    typeof window !== "undefined" && getAccessToken() ? "/auth/me" : null,
    apiFetch,
    { refreshInterval: 5 * 60 * 1000 }, // 5 dk
  );
  return { user: data, error, isLoading, mutate };
}

export function logout() {
  clearTokens();
  if (typeof window !== "undefined") {
    window.location.href = "/login";
  }
}

export interface RequireRoleProps {
  roles: CurrentUser["role"][];
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

export function RequireRole({ roles, children, fallback }: RequireRoleProps) {
  const { user, isLoading } = useCurrentUser();
  const router = useRouter();

  React.useEffect(() => {
    if (!isLoading && user && !roles.includes(user.role)) {
      router.replace("/");
    }
  }, [user, isLoading, roles, router]);

  if (isLoading) {
    return (
      <div className="p-4 text-textmut text-[13px]">Yetki kontrol ediliyor...</div>
    );
  }
  if (!user) {
    return fallback ?? (
      <div className="p-4 text-textmut text-[13px]">Giriş gerekli.</div>
    );
  }
  if (!roles.includes(user.role)) {
    return fallback ?? null;
  }
  return <>{children}</>;
}
