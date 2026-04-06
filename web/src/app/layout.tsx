import type { Metadata } from "next";
import { GeistMono } from "geist/font/mono";
import { ThemeProvider } from "@/components/theme-provider";
import "./globals.css";
import "./fallback-shell.css";

export const metadata: Metadata = {
  title: "AI Trading Bot Pro Max Ultra Plus 9000",
  description: "Paper trading dashboard: FinBERT news, technicals, ML, and SQLite history.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="stylesheet" href="/critical-shell.css" />
      </head>
      <body className={`min-h-screen ${GeistMono.className}`} suppressHydrationWarning>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
