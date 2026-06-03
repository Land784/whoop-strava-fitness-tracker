import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Midnight OLED dark neutrals. Accents reuse Tailwind's built-in
        // emerald-400 / sky-400 / rose-400 / amber-400, which match our palette.
        ink: "#05070D",
        panel: "#0E1525",
        panel2: "#131C30",
        line: "rgba(255,255,255,0.08)",
        // Kept for not-yet-restyled pages so their classes still resolve.
        brand: {
          50: "#f0f9ff",
          100: "#e0f2fe",
          500: "#38bdf8",
          600: "#0ea5e9",
          700: "#0284c7",
          900: "#0c4a6e",
        },
      },
      fontFamily: {
        // CSS variables provided by next/font (see app/layout.tsx).
        display: ["var(--font-display)", "ui-sans-serif", "system-ui", "sans-serif"],
        body: ["var(--font-body)", "ui-sans-serif", "system-ui", "sans-serif"],
        sans: ["var(--font-body)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 18px rgba(52,211,153,0.45)",
      },
    },
  },
  plugins: [],
};

export default config;
