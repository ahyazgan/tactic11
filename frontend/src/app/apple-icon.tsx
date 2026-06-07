import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%", height: "100%", display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center",
          background: "#0c0e14", color: "#fff", fontSize: 84, fontWeight: 900,
        }}
      >
        m2
        <div style={{ width: 90, height: 8, borderRadius: 4, background: "#e30613", marginTop: 8 }} />
      </div>
    ),
    { ...size },
  );
}
