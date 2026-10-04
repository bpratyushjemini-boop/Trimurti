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
          bg: '#060911',
          surface: '#0a101f',
          card: '#0d1527',
          cardHover: '#131e38',
          border: 'rgba(0, 240, 255, 0.14)',
          borderBright: 'rgba(0, 240, 255, 0.40)',
          borderMuted: 'rgba(255, 255, 255, 0.08)',
          cyan: '#00f0ff',
          cyanDim: '#0284c7',
          cyanGlow: 'rgba(0, 240, 255, 0.06)',
          blue: '#38bdf8',
          text: '#f1f5f9',
          textMuted: '#94a3b8',
          textDim: '#475569',
          // Indian Identity Palette
          saffron: '#FF6B00',
          saffronDim: 'rgba(255, 107, 0, 0.6)',
          saffronGlow: 'rgba(255, 107, 0, 0.08)',
          gold: '#FFD700',
          goldDim: 'rgba(255, 215, 0, 0.5)',
          sacred: '#FF8C00',
          sacredGlow: 'rgba(255, 140, 0, 0.1)',
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
        'hud-saffron': '0 0 15px -3px rgba(255, 107, 0, 0.12), 0 4px 6px -4px rgba(0, 0, 0, 0.5)',
        'glow-cyan': '0 0 20px rgba(0, 240, 255, 0.3)',
        'glow-saffron': '0 0 20px rgba(255, 107, 0, 0.25)',
        'glow-gold': '0 0 12px rgba(255, 215, 0, 0.2)',
      },
      backgroundImage: {
        'gradient-saffron-cyan': 'linear-gradient(135deg, #FF6B00, #00a2ffff)',
        'gradient-hero': 'radial-gradient(ellipse at 50% 40%, rgba(0, 240, 255, 0.08) 0%, rgba(255, 107, 0, 0.04) 40%, transparent 70%)',
        'gradient-panel': 'linear-gradient(180deg, rgba(255, 107, 0, 0.03) 0%, transparent 30%)',
      },
      animation: {
        'glow-breathe': 'glow-breathe 6s ease-in-out infinite',
        'float': 'float 4s ease-in-out infinite',
        'gradient-shift': 'gradient-shift 3s ease infinite',
        'shimmer': 'shimmer 3s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
