import { Providers } from "@/components/Providers";
import type { Metadata } from "next";
import { DM_Sans, Space_Grotesk } from "next/font/google";
import "./globals.css";

// next/font self-hosts these at build time: no runtime request to Google, no
// layout shift, and each is exposed as a CSS variable we wire into Tailwind's
// fontFamily (see tailwind.config.ts).
const display = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const body = DM_Sans({
  subsets: ["latin"],
  variable: "--font-body",
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "FitTracker — Whoop + Strava",
  description: "Unified fitness dashboard with AI insights",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
