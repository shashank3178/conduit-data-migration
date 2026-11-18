import Link from "next/link";
import { auth0 } from "@/lib/auth0";
import { ArrowRight, ArrowUpRight, Check, Database, GitBranch, ShieldCheck, Sparkles, Workflow } from "lucide-react";

export default async function HomePage() {
  const session = await auth0.getSession();
  return (
    <main className="min-h-screen overflow-hidden bg-[#101828] text-white">
      <div className="conduit-grid-bg pointer-events-none fixed inset-0 opacity-40"/>
      <div className="pointer-events-none absolute -right-40 -top-40 h-[520px] w-[520px] rounded-full bg-indigo-600/20 blur-[120px]"/>
      <div className="relative mx-auto max-w-7xl px-6">
        <header className="flex h-20 items-center justify-between border-b border-white/10">
          <Link href="/" className="flex items-center gap-3"><span className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500"><Database size={19}/></span><span><span className="block text-base font-bold tracking-[.16em]">CONDUIT</span><span className="block text-[9px] font-semibold uppercase tracking-[.2em] text-slate-400">Data migration</span></span></Link>
          <div className="flex items-center gap-3">{session ? <Link href="/dashboard" className="rounded-xl bg-white px-4 py-2.5 text-xs font-semibold text-slate-900 hover:bg-indigo-50">Open workspace <ArrowUpRight size={14} className="ml-1 inline"/></Link> : <a href="/auth/login?returnTo=/dashboard" className="rounded-xl border border-white/15 px-4 py-2.5 text-xs font-semibold text-white hover:bg-white/10">Sign in</a>}</div>
        </header>
        <section className="grid min-h-[650px] items-center gap-14 py-20 lg:grid-cols-[1.1fr_.9fr]">
          <div className="relative z-10">
            <div className="inline-flex items-center gap-2 rounded-full border border-indigo-300/20 bg-indigo-400/10 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[.16em] text-indigo-200"><Sparkles size={12}/> Enterprise migration workspace</div>
            <h1 className="mt-7 max-w-2xl text-5xl font-semibold leading-[1.08] tracking-[-.04em] sm:text-6xl">Your data.<br/><span className="bg-gradient-to-r from-indigo-300 via-sky-200 to-cyan-200 bg-clip-text text-transparent">Moving forward.</span></h1>
            <p className="mt-6 max-w-xl text-base leading-7 text-slate-300">Plan, execute, and validate database migrations through one clear operational workflow. Built for teams that need visibility at every step.</p>
            <div className="mt-9 flex flex-wrap gap-3">{session ? <Link href="/dashboard" className="rounded-xl bg-indigo-500 px-6 py-3.5 text-sm font-semibold text-white shadow-xl shadow-indigo-950/40 transition hover:-translate-y-0.5 hover:bg-indigo-400">Go to workspace <ArrowRight size={16} className="ml-2 inline"/></Link> : <a href="/auth/login?returnTo=/dashboard" className="rounded-xl bg-indigo-500 px-6 py-3.5 text-sm font-semibold text-white shadow-xl shadow-indigo-950/40 transition hover:-translate-y-0.5 hover:bg-indigo-400">Get started <ArrowRight size={16} className="ml-2 inline"/></a>}<a href="#workflow" className="rounded-xl border border-white/15 px-6 py-3.5 text-sm font-semibold text-slate-200 hover:bg-white/5">Explore workflow</a></div>
            <div className="mt-12 flex flex-wrap gap-x-6 gap-y-3 text-xs text-slate-400"><span className="inline-flex items-center gap-2"><Check size={14} className="text-emerald-400"/> Schema discovery</span><span className="inline-flex items-center gap-2"><Check size={14} className="text-emerald-400"/> Batch execution</span><span className="inline-flex items-center gap-2"><Check size={14} className="text-emerald-400"/> Data reconciliation</span></div>
          </div>
          <div className="relative">
            <div className="absolute -inset-8 rounded-[36px] bg-indigo-500/10 blur-2xl"/>
            <div className="relative rounded-[26px] border border-white/10 bg-[#1b2942]/90 p-5 shadow-2xl shadow-black/30 backdrop-blur-xl sm:p-7">
              <div className="flex items-center justify-between border-b border-white/10 pb-5"><div><p className="text-[10px] font-semibold uppercase tracking-[.16em] text-slate-400">Migration pipeline</p><p className="mt-1 text-sm font-semibold">Production data workflow</p></div><span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1 text-[10px] font-semibold text-emerald-300">Operational view</span></div>
              <div className="space-y-3 py-6">
                <PipelineStep number="01" title="Source discovery" subtitle="Inspect schemas, tables & columns" icon={<Database size={17}/>} status="Connected"/>
                <div className="ml-6 h-5 border-l border-dashed border-indigo-300/40"/>
                <PipelineStep number="02" title="Mapping & planning" subtitle="Align columns and validate target schema" icon={<GitBranch size={17}/>} status="Configure"/>
                <div className="ml-6 h-5 border-l border-dashed border-indigo-300/40"/>
                <PipelineStep number="03" title="Batch execution" subtitle="Checkpointed transfer with row-level errors" icon={<Workflow size={17}/>} status="Execute"/>
                <div className="ml-6 h-5 border-l border-dashed border-indigo-300/40"/>
                <PipelineStep number="04" title="Reconciliation" subtitle="Compare source and destination records" icon={<ShieldCheck size={17}/>} status="Verify"/>
              </div>
              <div className="grid grid-cols-3 gap-2 border-t border-white/10 pt-5"><MiniStat label="Write modes" value="2"/><MiniStat label="Run reports" value="CSV + JSON"/><MiniStat label="Progress" value="Live"/></div>
            </div>
          </div>
        </section>
        <section id="workflow" className="grid gap-4 border-t border-white/10 py-12 sm:grid-cols-3">
          <Feature icon={<Database size={18}/>} title="Understand your data" description="Discover database structure and choose exactly what moves."/>
          <Feature icon={<Workflow size={18}/>} title="Control the migration" description="Configure mappings, write strategies, and batch execution."/>
          <Feature icon={<ShieldCheck size={18}/>} title="Verify the outcome" description="Track inserted, updated, skipped, and failed records with reconciliation."/>
        </section>
        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-white/10 py-6 text-[10px] text-slate-500"><span>© CONDUIT · Enterprise Data Migration Platform</span><span>Discover · Plan · Execute · Validate</span></footer>
      </div>
    </main>
  );
}

function PipelineStep({number,title,subtitle,icon,status}:{number:string;title:string;subtitle:string;icon:React.ReactNode;status:string}) {
  return <div className="flex items-center gap-3 rounded-2xl border border-white/[.08] bg-white/[.035] p-3.5"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-400/15 text-indigo-200">{icon}</span><span className="min-w-0 flex-1"><span className="block text-xs font-semibold">{title}</span><span className="mt-1 block text-[10px] text-slate-400">{subtitle}</span></span><span className="text-[9px] font-semibold uppercase tracking-wider text-slate-500">{number}</span></div>;
}
function MiniStat({label,value}:{label:string;value:string}) { return <div className="rounded-xl bg-white/[.04] px-3 py-2.5"><p className="text-[9px] uppercase tracking-wider text-slate-500">{label}</p><p className="mt-1 text-xs font-semibold text-slate-200">{value}</p></div>; }
function Feature({icon,title,description}:{icon:React.ReactNode;title:string;description:string}) { return <div className="rounded-2xl border border-white/10 bg-white/[.035] p-5"><span className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-400/15 text-indigo-200">{icon}</span><h2 className="mt-4 text-sm font-semibold">{title}</h2><p className="mt-2 text-xs leading-5 text-slate-400">{description}</p></div>; }
