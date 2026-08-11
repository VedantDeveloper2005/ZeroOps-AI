import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type SurfaceProps = HTMLAttributes<HTMLDivElement> & {
  interactive?: boolean;
};

export function Surface({ interactive = false, className, ...props }: SurfaceProps) {
  return (
    <div
      className={cn(interactive ? "ops-surface-interactive" : "ops-surface", className)}
      {...props}
    />
  );
}
