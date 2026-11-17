"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity, ArrowUpRight, Boxes, Cable, ChevronDown,
  CircleHelp, Database, LayoutDashboard, LogOut, Sparkles, Workflow,
} from "lucide-react";

const navigation = [
  { label: "Workspace", items: [
    { label: "Overview", href: "/dashboard", icon: LayoutDashboard },
    { label: "Projects", href: "/dashboard/projects", icon: Boxes },
    { label: "Connections", href: "/dashboard/connections", icon: Cable },
  ]},
  { label: "Migrations", items: [
    { label: "Migration plans", href: "/dashboard/migration-planning", icon: Workflow },
    { label: "Run activity", href: "/dashboard/activity", icon: Activity },
    { label: "Validation", href: "/dashboard/validation", icon: ShieldCheck },
  ]},
];

export default function AppShell({
  children,
  userLabel,
}: {
  children: React.ReactNode;
  userLabel?: string | null;
}) {
  const pathname = usePathname();

  return (
    <div className="conduit-shell min-h-screen bg-[#f5f7fb] text-slate-900">
      <aside className="conduit-sidebar fixed inset-y-0 left-0 z-40 hidden w-[252px] flex-col border-r border-white/10 bg-[#101828] text-white lg:flex">
        <Link href="/dashboard" className="flex h-[76px] items-center gap-3 border-b border-white/10 px-6">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500 shadow-lg shadow-indigo-950/40">
            <Database size={19} strokeWidth={2.4} />
          </span>
          <span className="min-w-0">
            <span className="block text-[17px] font-bold tracking-[0.12em]">CONDUIT</span>
            <span className="block text-[9px] font-semibold uppercase tracking-[0.2em] text-slate-400">Data migration</span>
          </span>
        </Link>

        <div className="px-4 pt-6">
          <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.06] px-3 py-3">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-400/15 text-indigo-300"><Boxes size={16}/></span>
            <span className="min-w-0 flex-1">
              <span className="block text-xs font-semibold text-white">Workspace</span>
              <span className="block truncate text-[11px] text-slate-400">Personal environment</span>
            </span>
            <ChevronDown size={14} className="text-slate-500"/>
          </div>
        </div>

        <nav className="flex-1 space-y-7 overflow-y-auto px-4 py-7">
          {navigation.map((group) => (
            <div key={group.label}>
              <p className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">{group.label}</p>
              <div className="space-y-1">
                {group.items.map((item) => {
                  const active = item.href === "/dashboard"
                    ? pathname === item.href
                    : pathname === item.href || pathname.startsWith(item.href + "/");
                  const Icon = item.icon;
                  return (
                    <Link key={item.href} href={item.href}
                      className={`group flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium transition ${active ? "bg-indigo-500 text-white shadow-lg shadow-indigo-950/25" : "text-slate-400 hover:bg-white/[0.07] hover:text-white"}`}>
                      <Icon size={17} strokeWidth={1.9} className={active ? "text-white" : "text-slate-500 group-hover:text-slate-200"}/>
                      <span className="flex-1">{item.label}</span>
                      {active && <span className="h-1.5 w-1.5 rounded-full bg-white"/>}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className="m-4 rounded-2xl border border-white/10 bg-gradient-to-br from-indigo-500/20 to-sky-500/5 p-4">
          <div className="mb-3 flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-400/20 text-indigo-200"><Sparkles size={16}/></div>
          <p className="text-xs font-semibold text-white">Migration workspace</p>
          <p className="mt-1 text-[11px] leading-5 text-slate-400">Plan carefully. Move confidently. Validate every row.</p>
          <Link href="/dashboard/migration-planning" className="mt-3 inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-300 hover:text-white">Open planner <ArrowUpRight size={13}/></Link>
        </div>
        <div className="border-t border-white/10 px-5 py-4 text-[10px] text-slate-500">CONDUIT · MVP workspace</div>
      </aside>

      <div className="min-h-screen lg:pl-[252px]">
        <header className="sticky top-0 z-30 flex h-[76px] items-center justify-between border-b border-slate-200/80 bg-white/90 px-5 backdrop-blur-xl sm:px-8">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-50 text-indigo-700 lg:hidden"><Database size={18}/></div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">Workspace / CONDUIT</p>
              <p className="text-sm font-semibold text-slate-800">Migration operations</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 sm:flex">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500"/>
              <span className="text-[11px] font-semibold text-emerald-700">Workspace active</span>
            </div>
            <button aria-label="Help" className="hidden h-9 w-9 items-center justify-center rounded-xl border border-slate-200 text-slate-500 hover:bg-slate-50 sm:flex"><CircleHelp size={17}/></button>
            <div className="flex items-center gap-2 border-l border-slate-200 pl-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-900 text-[11px] font-bold text-white">{(userLabel?.[0] ?? "U").toUpperCase()}</div>
              <div className="hidden max-w-[150px] sm:block">
                <p className="truncate text-xs font-semibold text-slate-800">{userLabel ?? "Workspace user"}</p>
                <p className="text-[10px] text-slate-400">Administrator</p>
              </div>
              <a href="/auth/logout" aria-label="Log out" title="Log out" className="ml-1 flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"><LogOut size={16}/></a>
            </div>
          </div>
        </header>

        <div className="border-b border-slate-200 bg-white px-4 py-2.5 lg:hidden">
          <nav className="flex gap-2 overflow-x-auto">
            {navigation.flatMap((group) => group.items).map((item) => {
              const active = pathname === item.href || (item.href !== "/dashboard" && pathname.startsWith(item.href));
              return <Link key={item.href} href={item.href} className={`whitespace-nowrap rounded-lg px-3 py-2 text-xs font-semibold ${active ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-600"}`}>{item.label}</Link>;
            })}
          </nav>
        </div>

        <main className="mx-auto w-full max-w-[1500px] px-4 py-7 sm:px-7 sm:py-9 xl:px-10">{children}</main>
      </div>
    </div>
  );
}
