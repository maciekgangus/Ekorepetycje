/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: ["./app/templates/**/*.html"],
  theme: {
    extend: {
      colors: {
        cream: '#f7f4ef',
        ink: '#1a1814',
        navy: '#1a2744',
        gold: '#b8922a',
      },
      fontFamily: {
        sans: ['DM Sans', 'system-ui', 'sans-serif'],
        serif: ['Playfair Display', 'Georgia', 'serif'],
        inter: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
