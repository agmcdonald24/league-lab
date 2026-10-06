# Writing a post for the isuckatfantasy blog

This folder is the blog. Each post is one markdown file; the site reads the folder when it starts. **Push to publish**:
commit the file to `main`, and the next deploy serves it at `https://isuckatfantasy.io/blog/<slug>`. (How it works and
its limits: `docs/BLOG.md`.)

## 1. Name the file

`blog/<yyyy-mm-dd>-<slug>.md` — the date, then the address of the post in lower-case words joined by hyphens:

    blog/2026-10-13-week-6-receivers-to-start.md   →   isuckatfantasy.io/blog/week-6-receivers-to-start

Only `a–z`, `0–9` and single hyphens in the slug (80 characters at most). Two posts cannot share a slug. Copy
`_template.md` to start (files starting with `_` and this README are never posts).

## 2. The front matter

The lines between the two `---` at the top:

```
---
title: Week 6: the receivers to start          (required; 140 characters at most)
date: 2026-10-13                               (shown on the post; newest first in the list)
summary: One or two sentences for the list and the link preview.
author: Andrew                                 (left out: "isuckatfantasy")
tags: [matchups, receivers]                    (up to 8, lower case)
draft: true                                    (true = not published; remove or set false to publish)
image: week6-chart.png                         (optional: the picture for link previews, from blog/img/)
---
```

## 3. Write

Plain markdown: `## headings`, **bold**, lists (`- ` or `1. `), `> quotes`, tables, code in back-ticks, a line of
`---` for a break, and links.

- **A player**: link his page and it opens his card like everywhere on the site:
  `[Puka Nacua](/player/00-0039075)`. (His id is the end of his page's address on the site.)
- **Any page of the site**: `[the trade calculator](/trade-calc?league=ref:half)`.
- **Outside links** work for the sites the app already links to (ESPN, Sleeper, NFL.com …); others show as text.
- No raw HTML: it is shown as text, never run.

## 4. Pictures

Put the file in `blog/img/` (a `.png`, `.jpg` or `.webp`, under 2 MB, a name in lower case with hyphens:
`week6-chart.png`) and use it in the post:

    ![What the chart shows, in words](/blog/img/week6-chart.png)

SVG files are refused (they can carry code). A picture is cached for 30 days: to change one, save it under a new name.

## 5. Check it before you push

With the app running on your laptop, `LEAGUE_LAB_BLOG_DRAFTS=on` shows drafts too; open `/blog`. Then set
`draft: false` (or remove the line), commit and push.
