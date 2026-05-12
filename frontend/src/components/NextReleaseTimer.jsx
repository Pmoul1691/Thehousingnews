import React, { useEffect, useState } from "react";
import api from "@/lib/api";

function formatLocal(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const opts = { hour: "numeric", minute: "2-digit", timeZone: "America/Chicago" };
    return new Intl.DateTimeFormat("en-US", opts).format(d).toLowerCase().replace(" ", "");
  } catch {
    return "";
  }
}

export default function NextReleaseTimer({ compact = false }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    let mounted = true;
    api.get("/release-window").then((r) => mounted && setData(r.data)).catch(() => {});
    const id = setInterval(() => {
      api.get("/release-window").then((r) => mounted && setData(r.data)).catch(() => {});
    }, 60_000);
    return () => { mounted = false; clearInterval(id); };
  }, []);

  if (!data) return null;
  const label = formatLocal(data.next_release_iso);
  return (
    <div data-testid="next-release-window" className={`flex items-center gap-2 ${compact ? "" : "px-3 py-1.5 border border-gold-mid rounded-sm bg-cream"}`}>
      <span className="uppercase-label">next release</span>
      <span className="font-sans text-sm font-medium ink">{label} CT</span>
    </div>
  );
}
