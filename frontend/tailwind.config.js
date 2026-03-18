/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        werewolf: "#ef4444",
        villager: "#3b82f6",
        seer: "#a855f7",
        witch: "#22c55e",
        hunter: "#eab308",
      },
    },
  },
  plugins: [],
};
