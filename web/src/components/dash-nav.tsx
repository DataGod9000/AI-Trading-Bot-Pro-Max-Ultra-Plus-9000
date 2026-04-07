"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Overview" },
  { href: "/news", label: "News sentiment" },
  { href: "/ml", label: "Machine Learning" },
  { href: "/technical", label: "Techincal Analyst" },
  { href: "/backtesting", label: "Backtesting" },
  { href: "/paper-trading", label: "Paper trading" },
  { href: "/trades", label: "Trade history" },
  { href: "/analysis", label: "Market analysis" },
];

export function DashNav() {
  const pathname = usePathname();
  return (
    <aside className="btc-sidebar">
      <div className="btc-sidebar-title" title="AI Trading Bot Pro Max Ultra Plus 9000">
        AI Trading Bot Pro Max Ultra Plus 9000
      </div>
      <nav className="btc-sidebar-nav">
        {links.map((l) => {
          const active = pathname === l.href;
          return (
            <Link
              key={l.href}
              href={l.href}
              className={active ? "btc-nav-link btc-nav-link--active" : "btc-nav-link"}
            >
              {l.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
