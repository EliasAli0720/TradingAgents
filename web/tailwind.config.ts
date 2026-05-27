import type { Config } from 'tailwindcss';

// Palette mirrors Streamlit dark theme + docs/ui-guidelines.md semantic colors.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Streamlit dark theme
        bg: '#0e1117',
        panel: '#262730',
        border: '#3a3d46',
        muted: '#a3a8b8',
        text: '#fafafa',
        // Semantic (ui-guidelines.md §5)
        success: '#4CAF50',
        successBg: '#1b2a1d',
        danger: '#F44336',
        dangerBg: '#2a1818',
        info: '#2196F3',
        infoBg: 'rgba(33,150,243,0.08)',
        warn: '#FFB300',
        warnBg: '#2a2417',
        neutral: '#37474F',
        neutralBg: '#1c2126',
        research: '#7B1FA2',
        risk: '#0D47A1',
      },
      fontFamily: {
        sans: [
          '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"',
          'Roboto', '"Helvetica Neue"', 'sans-serif',
        ],
        mono: [
          'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco',
          'Consolas', 'monospace',
        ],
      },
    },
  },
  plugins: [],
} satisfies Config;
