/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // `DEFAULT`/`foreground` make bg-primary/text-primary/text-primary-foreground
        // resolve (shadcn convention, theme-able via the CSS variables in
        // index.css); the numeric 50-900 keys are the Savanna forest-green
        // scale (800 = #0B4D33) for any literal bg-primary-600 use.
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
          50: '#EDF7F1',
          100: '#D3EEDD',
          200: '#A8DCBD',
          300: '#73C497',
          400: '#43A872',
          500: '#238A57',
          600: '#136F45',
          700: '#0E5C3B',
          800: '#0B4D33',
          900: '#083A27',
        },
        // Savanna tokens from design/HANDOFF.md (light/dark values live in
        // index.css). Renamed where the handoff's name already means
        // something here: its `accent` (orange) is `sunset`, its `muted`
        // text colour is `muted-foreground`, its `primary`/`border`/`text`/
        // `bg` are primary / border / foreground / background.
        surface: "hsl(var(--card))",
        surface2: "rgb(var(--sv-surface2-rgb) / <alpha-value>)",
        "border-soft": "rgb(var(--sv-border-soft-rgb) / <alpha-value>)",
        "border-strong": "rgb(var(--sv-border-strong-rgb) / <alpha-value>)",
        faint: "rgb(var(--sv-faint-rgb) / <alpha-value>)",
        sunset: "rgb(var(--sv-accent-rgb) / <alpha-value>)",
        ok: {
          DEFAULT: "rgb(var(--sv-ok-rgb) / <alpha-value>)",
          bg: "rgb(var(--sv-ok-bg-rgb) / <alpha-value>)",
        },
        warn: {
          DEFAULT: "rgb(var(--sv-warn-rgb) / <alpha-value>)",
          bg: "rgb(var(--sv-warn-bg-rgb) / <alpha-value>)",
        },
        bad: {
          DEFAULT: "rgb(var(--sv-bad-rgb) / <alpha-value>)",
          bg: "rgb(var(--sv-bad-bg-rgb) / <alpha-value>)",
        },
        chip: "rgb(var(--sv-chip-rgb) / <alpha-value>)",
        mpesa: "rgb(var(--sv-mpesa-rgb) / <alpha-value>)",
        // Header band: stays deep green in dark mode too (slightly darker).
        band: "rgb(var(--sv-band-rgb) / <alpha-value>)",
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 4px)",
        sm: "calc(var(--radius) - 8px)",
        card: "20px",
        control: "999px",
      },
      boxShadow: {
        card: "var(--sv-shadow)",
      },
      fontFamily: {
        sans: ["'Plus Jakarta Sans'", "system-ui", "-apple-system", "'Segoe UI'", "Roboto", "sans-serif"],
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
