# yassineljakani.com — personal academic website

Personal website of **Dr. Yassin El Jakani** — Assistant Professor (Maître de
Conférences) at the Faculty of Sciences, Université Ibn Zohr, Agadir.
Research: Edge AI, IoT, cross-layer QoS prediction, physical-layer security.

Built with [Astro](https://astro.build/), [React](https://react.dev/),
[Tailwind CSS](https://tailwindcss.com/) and
[shadcn/ui](https://ui.shadcn.com/) components. Fully static output — deploy
the `dist/` folder on any host.

## 🚀 Quick start

```bash
npm install     # install dependencies (Node 22 recommended, see .node-version)
npm run dev     # local dev server at http://localhost:4321
npm run build   # production build into dist/
npm run preview # serve the production build locally
npm run check   # type-check the project
```

## ✏️ Where to edit content

**One file drives the whole site: [`src/data/profile.ts`](src/data/profile.ts).**
Name, tagline, research areas, positions, publications, talks, prizes,
certifications, teaching, community, navigation — all live there. You should
not need to touch components for normal content updates.

Search the codebase for **`TODO(input)`** to jump to every value waiting for
you.

## 📋 Inputs to fill (checklist)

| # | What | Where |
|---|------|-------|
| 1 | **Your domain** (once registered) | `astro.config.mjs` → `site`, and `public/robots.txt` |
| 2 | **Real CV PDF** (current one is a placeholder) | replace `public/cv.pdf` |
| 3 | **Event photos** — filenames are already wired in the data; just drop the files in | `public/images/` (see list below) |
| 4 | **Published email** — confirm `y.eljakani@uiz.ac.ma` is the address you want public | `src/data/profile.ts` → `profile.email` (also in `src/components/Footer.tsx`) |
| 5 | **Institution URLs** — verify faculty/lab links | `src/data/profile.ts` → `positions[].url`, `education[].schoolUrl` |
| 6 | **Earlier degrees** (Master's, Bachelor's) | `src/data/profile.ts` → `education` (commented example included) |
| 7 | **Institution logos** (optional) | drop files in `public/logos/`, set `logo: "/logos/uiz.png"` on positions/education |
| 8 | **Certification links** (optional) | `src/data/profile.ts` → add `url:` to any certification |
| 9 | **More social profiles — later** | `src/data/profile.ts` → uncomment `github`/`twitter`/`scholar`/`researchgate`/`orcid`; icon markup is also ready-but-commented in `Header.astro` and `Footer.tsx` |

> Social media is intentionally **LinkedIn-only** for now. Everything else is
> present in the code but commented out, so enabling it later is a one-line
> change. Uncommenting `scholar` or `researchgate` also automatically adds a
> "Full list on …" link under Publications.

### 📷 Photo files the site already expects

Drop these into `public/images/` (any of them can be skipped — a tasteful
"photo soon" tile shows until the file exists, and photos open in a lightbox
once present):

- **Devoxx 2025:** `devox20251.jfif`, `devox20252.jfif`, `devox20253.jfif`
- **Devoxx 2024:** `devox20241.jfif`, `devox20242.jfif`, `devox20243.jfif`
- **DevFest El Jadida:** `gdgjadida1.jfif`, `gdgjadida2.jfif`, `gdgjadida3.jfif`
- **DevFest Agadir:** `gdgdagadir1.jfif`, `gdgdagadir2.jfif`
- **GDSC ML sessions:** `ml1.jfif`
- **PhD defense:** `phd1.jfif` … `phd5.jfif`
- **Huawei Developer Competition:** `tech1.jfif` … `tech4.jfif`
- **Huawei ICT Competition:** `huawei1.jfif` … `huawei5.jfif`
- **Seeds for the Future:** `seeds1.jfif`, `seeds2.jfif`
- **MoroccoAI Summer School:** `ai1.jfif`, `ai2.jfif`

To change which photos belong to which item, edit the `images: [...]` arrays
in `src/data/profile.ts`.

## 🌐 Deploying

The build is fully static (`dist/`). Any of these work out of the box:

- **Netlify / Vercel / Cloudflare Pages:** connect the repo, build command
  `npm run build`, publish directory `dist`.
- **GitHub Pages / any web server:** upload the contents of `dist/`.

Remember input #1 (set your domain in `astro.config.mjs`) so the sitemap,
canonical URLs and social cards point to the right place.

## 🎨 Design

- Fonts: [Fraunces](https://fonts.google.com/specimen/Fraunces) (display serif)
  + [Inter](https://fonts.google.com/specimen/Inter) (body), inlined at build
  time.
- Palette: warm paper light mode / deep ink dark mode, violet accent, amber
  "signal" for years and dates — tokens in `src/styles/globals.css`.
- Layout/interaction framework adapted from the open-source personal site of
  [Yassine El Jakani](https://github.com/Eljakani/eljakani.me) (MIT, "feel
  free to fork"), rebuilt around an academic profile: Research, Publications,
  Talks with photo galleries, Prizes, Teaching and Community sections.

## 📄 License

Content (texts, publications data, photos, CV) © Dr. Yassin El Jakani.
Code adapted from Yassine El Jakani's MIT-licensed site template.
