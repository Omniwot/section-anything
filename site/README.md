# Section Anything website

A static, single-page site for the project. No build step, no frameworks, no external
requests: system fonts only, no analytics, no cookies.

```
site/
  index.html        page skeleton (headings and empty containers)
  assets/style.css  light and dark themes, responsive layout
  assets/app.js     fills the page from window.SA_DATA
  data/results.js   every number, table, example and list on the page
```

## Preview locally

From the project folder (`section-anything/`):

```sh
python3 -m http.server 8080 -d site
```

Then open http://localhost:8080. Stop the server with Ctrl+C.

You can also open `site/index.html` directly in a browser (file://). The data is loaded as a
plain script, not fetched as JSON, so this works without a server.

Theme: the page follows the system light/dark setting. The button in the top bar switches it
and remembers the choice in this browser (localStorage). Add `?theme=dark` or `?theme=light`
to the URL to force a theme for one view without saving it (handy for screenshots).

## Updating the numbers

The page shows only what is in `data/results.js`. Nothing is hard-coded in the HTML or
JavaScript, so after a new benchmark run:

1. Edit `data/results.js` (it defines `window.SA_DATA`). Change scores, dates, document
   counts and notes; add or remove rows in any `rows` array. Mark our own rows with
   `ours: true`.
2. Update `updated` at the top to the new date. It appears in the footer.
3. Reload the page and check the tables.

Notes:

- `repoUrl`: leave empty to hide every repository link; set it at launch to show them.
- Keep `where_others_win` and `limitations` current. They are shown in full on purpose.
- Text from the data file is inserted as plain text, so HTML in it is shown literally.
- READoc scores are drawn as bars on the full 0-100 Heading TEDS scale.

## Publishing on GitHub Pages (not done yet)

Nothing has been published. When the repository is public and you decide to publish:

1. Set `repoUrl` in `data/results.js`.
2. Commit the `site/` folder to the repository's default branch.
3. On GitHub: Settings > Pages > Build and deployment > Source: "GitHub Actions"
   (to deploy from `site/`) or "Deploy from a branch" with a `/docs` folder
   (in that case copy or move `site/` to `docs/`).
4. For the Actions route, add a workflow that uses `actions/upload-pages-artifact`
   with `path: site` and then `actions/deploy-pages`.
5. Open the Pages URL GitHub shows and check both themes and a phone-width view.
