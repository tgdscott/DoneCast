import * as React from "react"

import { cn } from "@/lib/utils"

const Input = React.forwardRef(({ className, type, ...props }, ref) => {
  const isFile = type === "file";
  const base = "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-base shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 md:text-sm";
  const fileEnhancements = isFile
    ? [
        // Remove the outer border/padding so only the file button gets outlined
        "border-0 p-0 h-auto",
        // Style only the Choose File button (pseudo-element)
        "file:mr-3 file:px-3 file:py-1.5 file:border file:border-input file:rounded-md file:bg-background file:text-sm file:font-medium file:text-foreground file:hover:bg-accent file:hover:text-accent-foreground file:cursor-pointer",
      ].join(" ")
    : "file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground";
  return (
    <input
      type={type}
      className={cn(base, fileEnhancements, className)}
      ref={ref}
      {...props}
    />
  );
})
Input.displayName = "Input"

export { Input }
