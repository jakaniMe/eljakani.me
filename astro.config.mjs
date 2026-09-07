import { defineConfig } from 'astro/config';
import react from "@astrojs/react";
import icon from "astro-icon";
import sitemap from '@astrojs/sitemap';

// Sitemap, canonical URLs and social-card URLs are generated from this value.
export default defineConfig({
  site: 'https://yassineljakani.com',
  integrations: [
    react(),
    icon(),
    sitemap()
  ],
  // Static output: the site builds to plain HTML/CSS/JS in `dist/`,
  // deployable on any static host (Netlify, Vercel, GitHub Pages, cPanel...).
  output: "static",
});
