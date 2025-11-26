import type React from "react"
import type { Metadata } from "next"
import { GeistSans } from "geist/font/sans"
import { GeistMono } from "geist/font/mono"
import { Analytics } from "@vercel/analytics/next"
import "./globals.css"
import { Suspense } from "react"
import { PostHogProvider } from "posthog-js/react"

export const metadata: Metadata = {
  title: "PodcastPlusPlus - Professional Podcast Hosting Made Simple",
  description:
    "The modern podcast hosting platform built for creators who want more. Unlimited uploads, advanced analytics, and powerful distribution tools.",
  generator: "v0.app",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body className={`font-sans ${GeistSans.variable} ${GeistMono.variable}`}>
        <PostHogProvider
          apiKey={process.env.NEXT_PUBLIC_POSTHOG_KEY}
          options={{
            api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST,
            defaults: '2025-05-24',
            capture_exceptions: true,
            debug: process.env.NODE_ENV === "development",
          }}
        >
          <Suspense fallback={null}>{children}</Suspense>
          <Analytics />
        </PostHogProvider>
      </body>
    </html>
  )
}