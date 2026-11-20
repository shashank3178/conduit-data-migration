"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { RefreshCw } from "lucide-react";

export default function AnalyticsRefresh({ runId }: { runId?: string }) {
  const router = useRouter();
  useEffect(() => {
    if (runId) {
      const stream = new EventSource("/api/analytics/runs/" + runId + "/stream");
      const refresh = () => router.refresh();
      stream.addEventListener("migration", refresh);
      stream.addEventListener("terminal", refresh);
      stream.onerror = refresh;
      return () => stream.close();
    }
    const timer = window.setInterval(() => router.refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [router, runId]);
  return <span className="inline-flex items-center gap-1 text-[10px] text-slate-400"><RefreshCw size={12}/> {runId ? "SSE live" : "Polling"}</span>;
}
