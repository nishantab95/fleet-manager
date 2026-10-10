import { ImageResponse } from "next/og";

export const alt = "Fleet AI Systems — construction fleet management software";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    <div style={{ width: "100%", height: "100%", display: "flex", position: "relative", overflow: "hidden", color: "#f7fbf9", background: "#092e2d", fontFamily: "Arial, sans-serif" }}>
      <div style={{ position: "absolute", width: 520, height: 520, borderRadius: 520, background: "#177466", opacity: 0.48, top: -250, right: -100 }} />
      <div style={{ position: "absolute", width: 360, height: 360, borderRadius: 360, background: "#d8912a", opacity: 0.16, bottom: -240, left: 390 }} />
      <div style={{ display: "flex", width: "100%", padding: "76px 82px", flexDirection: "column", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}><div style={{ display: "flex", width: 64, height: 64, border: "2px solid #79d6bd", borderRadius: 18, alignItems: "center", justifyContent: "center", color: "#79d6bd", fontSize: 26, fontWeight: 800 }}>FA</div><div style={{ display: "flex", flexDirection: "column", fontSize: 25, lineHeight: 1.05 }}><b>Fleet AI</b><span style={{ color: "#a7bbb5", letterSpacing: 4, fontSize: 16 }}>SYSTEMS</span></div></div>
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}><div style={{ display: "flex", color: "#e9b762", fontSize: 18, letterSpacing: 3, textTransform: "uppercase" }}>Construction fleet operations</div><div style={{ display: "flex", fontSize: 72, lineHeight: 1.02, fontWeight: 750, letterSpacing: -3, maxWidth: 930 }}>Run the field.<br />Read the fleet.</div></div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", color: "#b8cbc5", fontSize: 20 }}><span>Owners · Drivers · Supervisors · Maintenance</span><span>fleetaisystems.com</span></div>
      </div>
    </div>,
    size,
  );
}
