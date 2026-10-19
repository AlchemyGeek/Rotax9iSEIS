# Starting the app

SlingologyEIS runs in two ways. Both show the same screens and keep the same kind of workspace, and an
export from one opens in the other.

## In your browser, from the website

1. Open **https://alchemygeek.github.io/Rotax9iSEIS/app/** in Chrome or Safari on a Mac.
2. The first visit downloads the analysis engine — about 30 MB, once. The page shows its progress.
3. Create a workspace, then **Choose folder…** and pick the folder that holds your engine logs (or drop
   log files on the page). **Sync** analyses them.

Good to know:

- **Your logs stay on your computer.** The engine runs inside the browser; nothing is uploaded.
  Workspaces are kept in the browser's private storage for this site.
- **It works offline after the first visit.** Open the same address with no network and the app starts
  from your computer. When a new version is published, the next visit with a network switches to it
  and says *Updated to version …* once.
- **Safari asks for the folder again each visit.** The folder shows *Not connected — reconnect*; pick it
  again, then Sync. Chrome remembers the folder and may ask you to *Allow access* with one click.
- **Keep a backup.** The browser can clear a site's storage (for example when you clear browsing data).
  Settings → App → *Export all workspaces…* saves everything in one file you can import again.

## On your computer, as a local app

1. Install Python 3.10 or newer.
2. Download the `slingology_eis-….whl` file from the latest release on
   [GitHub](https://github.com/AlchemyGeek/Rotax9iSEIS/releases) and install it:

   ```bash
   pip install slingology_eis-*.whl
   ```

3. Start it, and open the address it prints (normally http://127.0.0.1:8420/):

   ```bash
   slingology-eis serve
   ```

Your workspaces are kept in a **SlingologyEIS** folder in your home folder. Settings → App → *Data
location* can move it. Add log folders by path; the app reads them where they are.

Stop the app with Ctrl-C in the terminal window.

## For the maintainer

### Publishing the website

Every push builds the site; CI keeps it as the artifact `slingology-eis` (`slingology-eis-site.zip`),
and a release tag attaches it to the release. The site is plain files: it works from any folder of any
static host, with no special server settings.

GitHub Pages serves this repository from the `gh-pages` branch, which the documentation already uses
(`mkdocs gh-deploy`, at https://alchemygeek.github.io/Rotax9iSEIS/). The app goes in the `app/` folder
of the same site:

```bash
rm -rf docs/app && mkdir -p docs/app
unzip slingology-eis-site.zip -d docs/app      # from the release, or a CI run's artifact
mkdocs gh-deploy                               # publishes the docs with the app under app/
```

`docs/app/` is not committed. Each publish adds the app's ~30 MB to the `gh-pages` branch history.

A custom domain is optional: set it in the repository's Settings → Pages. The app needs no change for
it — the address in the first section changes, nothing else.

### Tagging a release

1. Set the version in `pyproject.toml` and `slingology_eis/__init__.py` (kept equal), and update
   `CHANGELOG.md`.
2. Commit, then tag and push:

   ```bash
   git tag v1.2.3
   git push origin v1.2.3
   ```

3. CI builds the tag, creates the GitHub release if there isn't one yet, and attaches the wheel and the
   site zip to it. Edit the release notes on GitHub if you want more than "See CHANGELOG.md."
4. Publish the website from that release's site zip, as above.
