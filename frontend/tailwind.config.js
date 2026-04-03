/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        sidebar: {
          DEFAULT: "#0f172a",  // slate-900
          hover: "#1e293b",    // slate-800
          active: "#334155",   // slate-700
          text: "#94a3b8",     // slate-400
          textActive: "#f1f5f9", // slate-100
        },
      },
    },
  },
  plugins: [],
};
