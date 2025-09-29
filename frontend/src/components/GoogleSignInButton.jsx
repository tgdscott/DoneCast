import React from "react";
import { cn } from "@/lib/utils";

// Compliant Google sign-in button per branding guidelines:
// - Text: "Sign in with Google" (case-sensitive)
// - Use the multi-color "G" icon on a white button with a subtle border
// - Adequate padding, rounded corners, and clear separation from other elements
// - Do not alter the colors of the G icon
// - Minimum touch target 48x48px achieved via padding/height

export default function GoogleSignInButton({ href, className, ...props }) {
  return (
    <a href={href} className={cn("block", className)} {...props}>
      <div
        className={cn(
          "w-full inline-flex items-center justify-center gap-2", // 8px gap between G and text
          "rounded border bg-white", // 4px radius per guideline
          "hover:bg-[#f7f8f8]",
          "px-4 h-12", // 48px height target
          "transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#1a73e8]/40",
        )}
        role="button"
        aria-label="Sign in with Google"
        style={{ borderColor: "#dadce0" }}
      >
        <img
          src="/google-g-logo.svg"
          alt=""
          aria-hidden="true"
          className="h-[18px] w-[18px]"
          width={18}
          height={18}
        />
        <span className="text-sm font-medium" style={{ color: "#3c4043" }}>Sign in with Google</span>
      </div>
    </a>
  );
}
