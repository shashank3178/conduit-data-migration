"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity, ArrowUpRight, Boxes, Cable, ChartLine, Database, LayoutDashboard,
  LogOut, Workflow, ShieldCheck, Layers3,
} from "lucide-react";

const navigation = [
  { label: "Workspace", items: [
    { label: "Overview", href: "/dashboard", icon: LayoutDashboard },
    { label: "Projects", href: "/dashboard/projects", icon: Boxes },
    { label: "Connections", href: "/dashboard/connections", icon: Cable },
    { label: "Discovery", href: "/dashboard/discovery", icon: Database },
  ]},
  { label: "Migrations", items: [
    { label: "Migration plans", href: "/dashboard/migration-planning", icon: Workflow },
    { label: "Run activity", href: "/dashboard/activity", icon: Activity },
    { label: "Analytics", href: "/dashboard/analytics", icon: ChartLine },
    { label: "Database monitoring", href: "/dashboard/databases", icon: Database },
    { label: "Validation", href: "/dashboard/validation", icon: ShieldCheck },
  ]},
];

export default function AppShell({ children, userLabel }: { children: React.ReactNode; userLabel?: string | null }) {
  const pathname = usePathname();
  return (
    <div className="conduit-shell min-h-screen bg-[#fbf9f7] text-slate-900">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[248px] flex-col border-r border-slate-200 bg-white lg:flex">
        <Link href="/dashboard" className="flex h-[68px] items-center gap-3 border-b border-slate-200 px-5">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#fc6d26] text-white"><Database size={19}/></span>
          <span><span className="block text-[16px] font-bold tracking-tight text-slate-900">CONDUIT</span><span className="block text-[9px] font-semibold uppercase tracking-[.16em] text-slate-500">Data migration</span></span>
        </Link>
        <nav className="flex-1 space-y-7 overflow-y-auto px-3 py-6">
          {navigation.map(group=><div key={group.label}>
            <p className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[.12em] text-slate-400">{group.label}</p>
            <div className="space-y-0.5">{group.items.map(item=>{
              const active=item.href==="/dashboard"?pathname===item.href:pathname===item.href||pathname.startsWith(item.href+"/");
              const Icon=item.icon;
              return <Link key={item.href} href={item.href} className={`group flex items-center gap-3 rounded-md border-l-[3px] px-3 py-2.5 text-[13px] font-medium transition ${active?"border-[#fc6d26] bg-[#fff4ed] text-[#b84b12]":"border-transparent text-slate-600 hover:bg-slate-50 hover:text-slate-900"}`}>
                <Icon size={16} strokeWidth={1.9}/><span className="flex-1">{item.label}</span>{active&&<span className="h-1.5 w-1.5 rounded-full bg-[#fc6d26]"/>}
              </Link>;
            })}</div>
          </div>)}
        </nav>
        <div className="m-3 rounded-lg border border-slate-200 bg-[#fbf9f7] p-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-800"><Layers3 size={15} className="text-[#fc6d26]"/> Migration workspace</div>
          <p className="mt-2 text-[11px] leading-5 text-slate-500">Plan, execute and validate database migrations with observable checkpoints.</p>
          <Link href="/dashboard/migration-planning" className="mt-3 inline-flex items-center gap-1 text-[11px] font-semibold text-[#b84b12] hover:text-[#fc6d26]">Open planner <ArrowUpRight size={12}/></Link>
        </div>
        <div className="border-t border-slate-200 px-5 py-3 text-[10px] text-slate-400">CONDUIT · LOCAL WORKSPACE</div>
      </aside>
      <div className="min-h-screen lg:pl-[248px]">
        <header className="sticky top-0 z-30 flex h-[68px] items-center justify-between border-b border-slate-200 bg-white/95 px-4 backdrop-blur sm:px-7">
          <div className="flex items-center gap-3"><div className="flex h-8 w-8 items-center justify-center rounded-md bg-[#fff1e8] text-[#b84b12] lg:hidden"><Database size={17}/></div><div><p className="text-[10px] font-medium text-slate-400">CONDUIT / WORKSPACE</p><p className="text-sm font-semibold text-slate-800">Migration operations</p></div></div>
          <div className="flex items-center gap-3"><span className="hidden items-center gap-1.5 text-[11px] text-slate-500 sm:inline-flex"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500"/> Local environment</span><div className="flex items-center gap-2 border-l border-slate-200 pl-3"><div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-800 text-[11px] font-bold text-white">{(userLabel?.[0]??"U").toUpperCase()}</div><div className="hidden max-w-[150px] sm:block"><p className="truncate text-xs font-semibold text-slate-800">{userLabel??"Workspace user"}</p><p className="text-[10px] text-slate-400">Signed in</p></div><a href="/auth/logout" aria-label="Log out" title="Log out" className="ml-1 flex h-8 w-8 items-center justify-center rounded-md text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"><LogOut size={15}/></a></div></div>
        </header>
        <div className="border-b border-slate-200 bg-white px-3 py-2 lg:hidden"><nav className="flex gap-1 overflow-x-auto">{navigation.flatMap(group=>group.items).map(item=>{const active=pathname===item.href||(item.href!=="/dashboard"&&pathname.startsWith(item.href));return <Link key={item.href} href={item.href} className={`whitespace-nowrap rounded-md px-3 py-2 text-xs font-semibold ${active?"bg-[#fc6d26] text-white":"bg-slate-100 text-slate-600"}`}>{item.label}</Link>})}</nav></div>
        <main className="mx-auto w-full max-w-[1560px] px-4 py-6 sm:px-7 sm:py-8 xl:px-9">{children}</main>
      </div>
    </div>
  );
}
