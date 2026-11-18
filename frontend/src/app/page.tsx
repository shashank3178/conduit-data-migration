import Link from "next/link";
import { auth0 } from "@/lib/auth0";

export default async function HomePage() {
  const session = await auth0.getSession();
  return (
    <main className="run-artwash min-h-screen overflow-hidden text-[#f2eadb]">
      <header className="relative z-10 mx-auto flex max-w-7xl items-center justify-between px-6 py-7">
        <Link href="/" className="flex items-center gap-3 font-serif text-2xl tracking-[.18em]"><img src="/conduit-logo.png" alt="" className="h-10 w-10 object-contain" /> CONDUIT</Link>
        <span className="eyebrow hidden sm:block">A considered approach to data movement</span>
        {session ? <Link href="/dashboard" className="rounded-full border border-[#c8a66f]/50 px-5 py-2.5 text-sm text-[#f1e5d0] hover:bg-[#c8a66f]/10">Enter workspace ↗</Link> : <a href="/auth/login?returnTo=/dashboard" className="rounded-full border border-[#c8a66f]/50 px-5 py-2.5 text-sm text-[#f1e5d0] hover:bg-[#c8a66f]/10">Sign in ↗</a>}
      </header>
      <section className="relative mx-auto grid min-h-[78vh] max-w-7xl items-center gap-12 px-6 pb-20 pt-12 lg:grid-cols-[1.15fr_.85fr]">
        <div className="relative z-10">
          <p className="eyebrow">Enterprise data migration / Precision in every transfer</p>
          <h1 className="display-title mt-7 max-w-4xl font-serif text-7xl leading-[.94] md:text-[7.5rem]">Move data.<br/><em>Keep meaning.</em></h1>
          <p className="mt-8 max-w-xl text-lg leading-8 text-[#c7b99f]">A deliberate workspace for discovering databases, shaping migration plans, and observing every record as it moves.</p>
          <div className="mt-10 flex flex-wrap gap-4">
            <Link href={session ? "/dashboard" : "/auth/login?returnTo=/dashboard"} className="rounded-sm bg-[#c8a66f] px-7 py-4 text-sm font-bold uppercase tracking-[.12em] text-[#211b13] hover:bg-[#dec18f]">{session ? "Open workspace" : "Begin a migration"} ↗</Link>
            <Link href="/dashboard/migration-planning" className="rounded-sm border border-[#c8a66f]/45 px-7 py-4 text-sm font-semibold text-[#ead8b9] hover:bg-[#c8a66f]/10">Explore workflow</Link>
          </div>
          <div className="mt-16 grid max-w-xl grid-cols-3 border-t border-[#c8a66f]/25 pt-5">
            <div><strong className="font-serif text-3xl text-[#e8d3ad]">01</strong><p className="mt-1 text-[10px] uppercase tracking-[.16em] text-[#a99a80]">Discover</p></div>
            <div><strong className="font-serif text-3xl text-[#e8d3ad]">02</strong><p className="mt-1 text-[10px] uppercase tracking-[.16em] text-[#a99a80]">Design</p></div>
            <div><strong className="font-serif text-3xl text-[#e8d3ad]">03</strong><p className="mt-1 text-[10px] uppercase tracking-[.16em] text-[#a99a80]">Observe</p></div>
          </div>
        </div>
        <div className="relative hidden min-h-[540px] lg:block">
          <div className="absolute inset-5 border border-[#c8a66f]/30"/>
          <div className="absolute inset-10 border border-[#c8a66f]/15"/>
          <div className="absolute inset-0 bg-gradient-to-br from-[#c8a66f]/10 via-transparent to-[#8d4f2d]/20"/>
          <div className="absolute bottom-16 left-0 max-w-xs border-l-2 border-[#c8a66f] bg-[#18150f]/85 p-6 backdrop-blur-sm"><p className="eyebrow">The migration ledger</p><p className="mt-3 font-serif text-3xl leading-tight text-[#f1e5d0]">Every batch has a story.</p><p className="mt-3 text-sm leading-6 text-[#b9aa90]">Persistent progress, table-level detail, and payload telemetry—available after navigation or refresh.</p></div>
          <div className="absolute right-12 top-14 h-40 w-40 rounded-full border border-[#c8a66f]/40"/><div className="absolute right-[5.2rem] top-[5.2rem] h-36 w-36 rounded-full border border-[#c8a66f]/20"/>
        </div>
      </section>
      <footer className="mx-auto flex max-w-7xl flex-wrap justify-between gap-3 border-t border-[#c8a66f]/20 px-6 py-6 text-xs text-[#8f8068]"><span>CONDUIT / DATA MIGRATION ATELIER</span><span>Built for visibility, integrity, and control.</span></footer>
    </main>
  );
}
