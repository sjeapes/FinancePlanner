/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        navy:     '#0f1b2d',
        surface:  '#162236',
        elevated: '#1d2f47',
        border:   '#243859',
        teal:     '#0e9aad',
        gold:     '#d4a843',
        green:    '#2dbd7e',
        red:      '#e05252',
        purple:   '#a78bfa',
        slate:    '#8fa3b8',
        text:     '#e8edf2',
      },
      fontFamily: {
        display: ['"Playfair Display"', 'serif'],
        mono:    ['"DM Mono"', 'monospace'],
        sans:    ['"DM Sans"', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
