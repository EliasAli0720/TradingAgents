import type { Config } from 'tailwindcss';

// Palette follows AI_Huang_Caishen_Brand_Guidelines.md.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: '#051A10',
        panel: '#092E24',
        border: '#24493C',
        muted: '#C6CDBF',
        text: '#F7F4EA',
        brandGreen: '#0C3D2F',
        brandGold: '#DDAA53',
        brandGoldDark: '#C08933',
        brandGoldLight: '#F4D98B',
        success: '#2E8B57',
        successBg: '#0B2E1C',
        danger: '#C64B4B',
        dangerBg: '#311A1A',
        info: '#DDAA53',
        infoBg: 'rgba(221,170,83,0.12)',
        warn: '#F4D98B',
        warnBg: '#2F2612',
        neutral: '#3B563F',
        neutralBg: '#14251D',
        research: '#7B1FA2',
        risk: '#0D47A1',
      },
      fontFamily: {
        sans: [
          'Manrope', '"Noto Sans SC"', '"PingFang SC"', '"Microsoft YaHei"',
          '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'sans-serif',
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
