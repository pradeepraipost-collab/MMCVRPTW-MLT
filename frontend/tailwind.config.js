/** @type {import('tailwindcss').Config} */
// Kept verbatim from ui_reference per spec §7.2. The brand teal ramp is the
// design-token canon for the project; do not adjust without a corresponding
// spec change.
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  '#edfcf9',
          100: '#d2f7f1',
          200: '#aaeee4',
          300: '#72e0d2',
          400: '#3bcaba',
          500: '#1aaea0',
          600: '#108b82',
          700: '#126e69',
          800: '#145857',
          900: '#154947',
          950: '#052e2e',
        },
      },
      fontFamily: {
        sans: ['"Space Grotesk"', 'sans-serif'],
        display: ['"Syne"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
    },
  },
  plugins: [],
}
