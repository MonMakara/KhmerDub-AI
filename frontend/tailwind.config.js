/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        khmer: ['"Khmer OS Battambang"', '"Noto Sans Khmer"', '"Kantumruy Pro"', 'sans-serif'],
        battambang: ['"Khmer OS Battambang"', '"Noto Sans Khmer"', 'sans-serif'],
        muol: ['"Khmer OS Muol"', '"Noto Serif Khmer"', 'serif'],
        content: ['"Khmer OS Content"', '"Noto Sans Khmer"', 'sans-serif'],
      },
      colors: {
        brand: {
          50: '#eef2ff',
          100: '#e0e7ff',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
        }
      }
    },
  },
  plugins: [],
}
