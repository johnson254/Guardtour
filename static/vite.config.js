import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [tailwindcss()],
  root: '.',
  base: '/static/dist/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: {
        main: 'src/main.js',
        'pages/dashboard': 'src/pages/dashboard.js',
        'pages/dispatch': 'src/pages/dispatch.js',
        'pages/manage': 'src/pages/manage.js',
        'pages/routes': 'src/pages/routes.js',
        'pages/map-view': 'src/pages/map-view.js',
        'pages/guards': 'src/pages/guards.js',
        'pages/incidents': 'src/pages/incidents.js',
        'pages/login': 'src/pages/login.js',
        'pages/register': 'src/pages/register.js',
        'pages/reports': 'src/pages/reports.js',
        'pages/admin': 'src/pages/admin.js',
      },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
  },
});
