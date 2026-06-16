"use client";

/**
 * Doğrulama Rozeti — bir tahminin yanına "bu yöntem out-of-sample güven X'te
 * doğrulandı" provenance'ı koyar ve /calibration'a link verir. Tahminin
 * kanıt katmanına bağlı olduğunu tek bakışta gösterir.
 */

import * as React from "react";
import Link from "next/link";
import { VALIDATED_TRUST, VALIDATED_META, type TrustMarket } from "@/lib/validated-trust";

const COLOR = (t: number) => (t >= 70 ? "var(--low)" : t >= 50 ? "var(--mid)" : "var(--high)");

export function TrustBadge({ market = "result", note }: { market?: TrustMarket; note?: string }) {
  const trust = VALIDATED_TRUST[market];
  return (
    <Link
      href="/calibration"
      title={`Yöntem ${VALIDATED_META.method}, görülmemiş ${VALIDATED_META.season} sezonunda (${VALIDATED_META.matches} maç) doğrulandı. Detay için tıkla.`}
      style={{ display: "inline-flex", alignItems: "center", gap: 7, textDecoration: "none", background: "var(--panel3)", border: "1px solid var(--line)", borderRadius: 7, padding: "5px 9px", fontSize: 11 }}
    >
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: COLOR(trust), flexShrink: 0 }} />
      <span style={{ color: "var(--muted)" }}>
        Doğrulanmış yöntem · out-of-sample güven{" "}
        <b style={{ color: COLOR(trust), fontFamily: "JetBrains Mono" }}>{trust}</b>
        {note ? <span style={{ color: "var(--dim)" }}> · {note}</span> : null}
      </span>
      <span style={{ color: "var(--dim)", fontSize: 10 }}>kanıt →</span>
    </Link>
  );
}
