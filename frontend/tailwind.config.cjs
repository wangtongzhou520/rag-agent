/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "var(--canvas)",
        surface: "var(--surface)",
        ink: "var(--text-primary)",
        muted: "var(--text-secondary)",
        border: "var(--border)",
        brand: {
          50: "var(--blue-50)",
          100: "var(--blue-100)",
          200: "var(--blue-200)",
          300: "var(--blue-300)",
          400: "var(--blue-400)",
          500: "var(--blue-500)",
          600: "var(--blue-600)",
          700: "var(--blue-700)",
          800: "var(--blue-800)",
          900: "var(--blue-900)",
          950: "var(--blue-950)",
        },
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "Noto Sans SC", "Microsoft YaHei", "sans-serif"],
        mono: ["IBM Plex Mono", "SFMono-Regular", "Consolas", "monospace"],
      },
      boxShadow: {
        panel: "0 2px 8px rgb(16 42 86 / 6%)",
        floating: "0 12px 36px rgb(31 95 199 / 12%)",
        focus: "0 0 0 3px rgb(147 197 253 / 48%)",
      },
      keyframes: {
        "enter-up": {
          from: { opacity: "0", transform: "translateY(10px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "signal-flow": {
          from: { transform: "translateX(-120%)" },
          to: { transform: "translateX(420%)" },
        },
      },
      animation: {
        "enter-up": "enter-up 220ms ease-out both",
        "signal-flow": "signal-flow 2.8s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
