import LiveRunBeacon from "./live-run-beacon";

export default function DashboardLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <>{children}<LiveRunBeacon /></>;
}
