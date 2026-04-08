import { DashNav } from "@/components/dash-nav";

export default function AppShellLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <div className="btc-app-shell">
      <DashNav />
      <div className="btc-main min-w-0">
        {children}
      </div>
    </div>
  );
}
