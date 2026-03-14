import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'API Drift Agent',
  description: 'Detect breaking API changes in provider PRs and automatically open GitHub Issues in affected consumer repos.',
  base: '/api-drift-agent/',

  themeConfig: {
    nav: [
      { text: 'Guide', link: '/guide' },
      { text: 'CLI', link: '/cli' },
      { text: 'GitHub', link: 'https://github.com/DriftAgent/api-drift-agent' },
    ],

    sidebar: [
      {
        text: 'Getting Started',
        items: [
          { text: 'Guide', link: '/guide' },
          { text: 'Python CLI', link: '/cli' },
        ],
      },
      {
        text: 'Reference',
        items: [
          { text: 'Inputs', link: '/guide#inputs' },
          { text: 'Re-run Behaviour', link: '/guide#re-run-behaviour' },
          { text: 'Troubleshooting', link: '/guide#troubleshooting' },
        ],
      },
    ],

    socialLinks: [
      { icon: 'github', link: 'https://github.com/DriftAgent/api-drift-agent' },
    ],

    footer: {
      message: 'Released under the MIT License.',
    },
  },
})
