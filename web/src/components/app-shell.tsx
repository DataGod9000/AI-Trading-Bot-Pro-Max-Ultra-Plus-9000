"use client";

import { useEffect, useState } from "react";
import { DashNav } from "@/components/dash-nav";

const MIN_WIDTH = 980;

export function AppShell({ children }: { children: React.ReactNode }) {
  const [tooSmall, setTooSmall] = useState(false);

  useEffect(() => {
    const onResize = () => setTooSmall(window.innerWidth < MIN_WIDTH);
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  if (tooSmall) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-background px-6">
        <div className="w-full max-w-xl rounded-2xl border border-border bg-card p-10 text-center">
          <div className="text-xs font-semibold uppercase tracking-wide text-primary">Heads up</div>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white">
            This website is designed for desktop layouts
          </h1>
          <p className="mt-4 text-sm text-muted-foreground">
            not built for small screen because I have a life and a full time job outside of this passion project
          </p>
          <div className="mt-5 space-y-2 text-sm text-muted-foreground">
            <p>
              Try <strong className="text-foreground">zooming out</strong>, <strong className="text-foreground">making the window wider</strong>, or
              using a <strong className="text-foreground">computer</strong>.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="btc-app-shell">
      <DashNav />
      <div className="btc-main min-w-0">{children}</div>
    </div>
  );
}

