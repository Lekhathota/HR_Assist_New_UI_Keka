/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,jsx}', './public/index.html'],
  theme: {
    extend: {
      colors: {
        canvas: '#030712',
        orange: {
          light: '#FDBA74',
          DEFAULT: '#F97316',
          dark: '#EA580C',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
      },
      backgroundImage: {
        'gradient-heading': 'linear-gradient(90deg, #FFFFFF 0%, #F97316 100%)',
        'btn-primary': 'linear-gradient(90deg, #FFFFFF 0%, #FDBA74 35%, #F97316 100%)',
        'sidebar-active': 'linear-gradient(90deg, rgba(249,115,22,0.35) 0%, rgba(234,88,12,0.15) 100%)',
      },
      boxShadow: {
        glow: '0 0 40px rgba(249, 115, 22, 0.15)',
        'glow-sm': '0 0 24px rgba(249, 115, 22, 0.12)',
        card: '0 8px 32px rgba(0, 0, 0, 0.35)',
      },
      animation: {
        'float-slow': 'floatY 12s ease-in-out infinite',
        'pulse-soft': 'pulseScale 14s ease-in-out infinite',
        'rise': 'rise 18s linear infinite',
      },
      keyframes: {
        floatY: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-18px)' },
        },
        pulseScale: {
          '0%, 100%': { transform: 'scale(1)' },
          '50%': { transform: 'scale(1.05)' },
        },
        rise: {
          '0%': { transform: 'translateY(100%)', opacity: '0' },
          '10%': { opacity: '0.4' },
          '100%': { transform: 'translateY(-120vh)', opacity: '0' },
        },
      },
    },
  },
  plugins: [],
};
