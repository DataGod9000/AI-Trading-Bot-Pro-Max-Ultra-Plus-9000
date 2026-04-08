"use client";

import { DotLoader } from "@/components/ui/dot-loader";
import { cn } from "@/lib/utils";

const game = [
  [14, 7, 0, 8, 6, 13, 20],
  [14, 7, 13, 20, 16, 27, 21],
  [14, 20, 27, 21, 34, 24, 28],
  [27, 21, 34, 28, 41, 32, 35],
  [34, 28, 41, 35, 48, 40, 42],
  [34, 28, 41, 35, 48, 42, 46],
  [34, 28, 41, 35, 48, 42, 38],
  [34, 28, 41, 35, 48, 30, 21],
  [34, 28, 41, 48, 21, 22, 14],
  [34, 28, 41, 21, 14, 16, 27],
  [34, 28, 21, 14, 10, 20, 27],
  [28, 21, 14, 4, 13, 20, 27],
  [28, 21, 14, 12, 6, 13, 20],
  [28, 21, 14, 6, 13, 20, 11],
  [28, 21, 14, 6, 13, 20, 10],
  [14, 6, 13, 20, 9, 7, 21],
] as const;

export function Computing({
  label = "Computing…",
  className,
  dotClassName,
}: {
  label?: string;
  className?: string;
  dotClassName?: string;
}) {
  return (
    <div className={cn("flex items-center gap-3 text-muted-foreground", className)}>
      <DotLoader
        frames={game as unknown as number[][]}
        dotClassName={cn("bg-foreground/10 [&.active]:bg-foreground/85", dotClassName)}
      />
      <p className="text-xs font-medium">{label}</p>
    </div>
  );
}

