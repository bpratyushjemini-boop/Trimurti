/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        narad: {
          bg: '#060911',           // Deepest void / navy-black
          surface: '#0a101f',      // Dark HUD panel background
          card: '#0d1527',         // Slightly raised card background
          cardHover: '#131e38',    // Hover state on cards/items
          border: 'rgba(0, 240, 255, 0.14)',      // Hairline cyan border
          borderBright: 'rgba(0, 240, 255, 0.40)',// Active / focused border
          borderMuted: 'rgba(255, 255, 255, 0.08)',
          cyan: '#00f0ff',         // Electric iconic cyan accent
          cyanDim: '#0284c7',      // Muted cyan for secondary elements
          cyanGlow: 'rgba(0, 240, 255, 0.06)',   // Subtle aura
          blue: '#38bdf8',         // Technical light blue
          text: '#f1f5f9',         // Crisp primary text
          textMuted: '#94a3b8',    // Muted technical labels
          textDim: '#475569',      // Monospace dim timestamps
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'SF Mono', 'Menlo', 'monospace'],
        display: ['Chakra Petch', 'Inter', 'sans-serif'],
      },
      boxShadow: {
        'hud-subtle': '0 0 15px -3px rgba(0, 240, 255, 0.08), 0 4px 6px -4px rgba(0, 0, 0, 0.5)',
        'hud-focus': '0 0 20px 0px rgba(0, 240, 255, 0.18)',
      },
    },
  },
  plugins: [],
}
