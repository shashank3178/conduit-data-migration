"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { loadLiveRuns } from "./monitor-actions";

export default function LiveRunBeacon() {
  const [count, setCount] = useState<number | null>(null);
  useEffect(() => {
    let alive = true;
    const refresh = async () => {
      try {
        const runs = await loadLiveRuns();
        if (alive) setCount(runs.filter((run: any) => ["queued", "running", "cancel_requested"].includes(run.status)).length);
      } catch { /* Authentication or API outages should not obstruct navigation. */ }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 8000);
    return () => { alive = false; window.clearInterval(timer); };
  }, []);
  return (
    <Link href="/dashboard/runs" className="fixed bottom-5 right-5 z-50 flex items-center gap-3 rounded-full border border-[#c8a66f]/50 bg-[#1d1a15]/95 px-4 py-3 text-sm text-[#f1e5d0] shadow-2xl backdrop-blur-md hover:border-[#e3c58f]">
      <span className={count ? "h-2.5 w-2.5 animate-pulse rounded-full bg-[#a9bd80]" : "h-2.5 w-2.5 rounded-full bg-[#9b8c72]"}/>
      <span>{count === null ? "Run observatory" : count ? `${count} active migration${count === 1 ? "" : "s"}` : "Run observatory"}</span>
      <span className="text-[#d4ad75]">↗</span>
    </Link>
  );
}
