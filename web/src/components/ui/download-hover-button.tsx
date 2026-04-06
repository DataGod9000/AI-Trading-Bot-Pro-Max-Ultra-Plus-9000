"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { Download, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

export type AnimatedDownloadButtonProps = {
  /** Link mode (default demo). Ignored when `onClick` is set. */
  href?: string;
  download?: boolean | string;
  /** Button mode — use for refresh/actions. */
  onClick?: () => void;
  disabled?: boolean;
  pending?: boolean;
  /** Text revealed on hover (or while pending). */
  label?: string;
  className?: string;
  /** Pixel width when expanded (long labels need more). */
  expandedWidth?: number;
  /** `download` = red pill + download icon; `primary` = monochrome (dark pill + white icon/text) for actions like refresh. */
  variant?: "download" | "primary";
};

export default function AnimatedDownloadButton({
  href = "#Your Download Link",
  download: downloadAttr,
  onClick,
  disabled = false,
  pending = false,
  label = "Download",
  className,
  expandedWidth = 220,
  variant = "download",
}: AnimatedDownloadButtonProps = {}) {
  const [isHovered, setIsHovered] = React.useState(false);
  const interactive = !disabled && !pending;
  const expanded = pending || (interactive && isHovered);
  const collapsed = 64;
  const targetW = expanded ? expandedWidth : collapsed;

  const shell = cn(
    variant === "primary"
      ? "border border-zinc-500/70 bg-zinc-950 text-zinc-50 shadow-md hover:border-zinc-300 hover:bg-zinc-900"
      : "bg-red-600",
    "flex items-center justify-center overflow-hidden relative px-3",
  );

  const IdleIcon = variant === "primary" ? RefreshCw : Download;
  const glyph = variant === "primary" ? "text-zinc-50" : "text-white";

  const inner = (
    <motion.div
      initial={false}
      animate={{ width: targetW, height: collapsed }}
      onHoverStart={() => interactive && setIsHovered(true)}
      onHoverEnd={() => setIsHovered(false)}
      transition={{ duration: 0.3 }}
      className={shell}
      style={{ borderRadius: 32 }}
    >
      {pending ? (
        <div className="flex w-full items-center justify-center gap-2 px-2">
          <RefreshCw className={cn("size-7 shrink-0 animate-spin", glyph)} aria-hidden />
          <span className={cn("whitespace-nowrap text-lg font-bold", glyph)}>Syncing…</span>
        </div>
      ) : (
        <>
          <motion.div
            className="absolute flex items-center justify-center"
            animate={{
              opacity: expanded ? 0 : 1,
              scale: expanded ? 0.8 : 1,
            }}
            transition={{ duration: 0.2 }}
          >
            <IdleIcon className={cn("size-8", glyph)} aria-hidden />
          </motion.div>

          <motion.div
            className="flex w-full items-center justify-center"
            initial={{ opacity: 0 }}
            animate={{
              opacity: expanded ? 1 : 0,
            }}
            transition={{ duration: 0.2, delay: expanded ? 0.1 : 0 }}
          >
            <span className={cn("whitespace-nowrap text-lg font-bold", glyph)}>{label}</span>
          </motion.div>
        </>
      )}
    </motion.div>
  );

  if (onClick) {
    return (
      <button
        type="button"
        className={cn(
          "relative inline-block shrink-0 rounded-full border-none bg-transparent p-0",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          disabled && "cursor-not-allowed opacity-60",
          className,
        )}
        disabled={disabled}
        aria-busy={pending}
        onClick={onClick}
      >
        {inner}
      </button>
    );
  }

  return (
    <a
      href={href}
      download={downloadAttr}
      className={cn("relative inline-block shrink-0", className)}
    >
      {inner}
    </a>
  );
}
