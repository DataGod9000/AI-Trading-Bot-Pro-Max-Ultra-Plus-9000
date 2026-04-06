"use client";

import * as React from "react";
import AnimatedDownloadButton from "@/components/ui/download-hover-button";

function DemoAnimatedDownloadButton() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <AnimatedDownloadButton />
    </div>
  );
}

export { DemoAnimatedDownloadButton };
