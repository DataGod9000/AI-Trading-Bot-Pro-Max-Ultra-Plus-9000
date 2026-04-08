import { DashNav } from "@/components/dash-nav";
import { SnapshotModeBanner } from "@/components/snapshot-mode-banner";

export default function AppShellLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <div className="btc-app-shell">
      <DashNav />
      <div className="btc-main min-w-0">
        <SnapshotModeBanner />
        {children}
      </div>
    </div>
  );
}
