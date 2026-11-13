/**
 * Tailwind config for the NETS production frontend.
 *
 * SCOPING CONTRACT (protects the legacy artifact design system):
 * 1. `corePlugins.preflight: false`  - Tailwind's global reset is OFF. It is the
 *    reset, not the utilities, that destroys foreign pages. Our own scoped reset
 *    lives in styles/globals.css under `.nets-next`.
 * 2. `important: "#nets-next-root"`   - every utility is emitted as
 *    `#nets-next-root .p-6 {...}`, so even if this stylesheet is ever loaded next
 *    to the legacy artifact (an embed, a migration page), no rule can touch
 *    anything outside the wrapper div.
 * 3. Dark mode is class-based (`.dark` on the wrapper), never media-query, so the
 *    host page's scheme cannot flip our components and vice versa.
 *
 * Every page/layout must render inside:
 *   <div id="nets-next-root" className="nets-next">...</div>
 */

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,jsx,ts,tsx}", "./components/**/*.{js,jsx,ts,tsx}"],
  darkMode: "class",
  important: "#nets-next-root",
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#16a34a", // NETS green
          dark: "#15803d",
          soft: "#f0fdf4",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.06)",
        drawer: "-16px 0 48px rgba(0,0,0,.2)",
      },
    },
  },
  plugins: [],
};
