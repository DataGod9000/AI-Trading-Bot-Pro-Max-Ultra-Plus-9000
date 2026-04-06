import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "News Sentimental Analysis",
};

export default function NewsLayout({ children }: { children: React.ReactNode }) {
  return children;
}
