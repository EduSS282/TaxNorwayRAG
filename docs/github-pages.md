# GitHub Pages

The public project website is **https://eduss282.github.io/TaxNorwayRAG/**.
Its source is `site/index.html` and `site/styles.css`: plain HTML/CSS with no build-time
dependencies, JavaScript, analytics, model calls or external font requests. The English
copy follows the repository documentation. It presents implemented capabilities and links
to the runbooks on GitHub; it is not a hosted tax question interface.

The header uses the repository's original `docs/assets/taxguide-logo.svg`, copied unchanged
to `site/assets/taxguide-logo.svg` for the isolated Pages artifact. When changing the logo,
update both copies; a regression test checks their byte-for-byte equality.

## Deployment

In GitHub, open **Settings → Pages → Build and deployment → Source → GitHub Actions**.
The `.github/workflows/pages.yaml` workflow publishes changes to `site/`, its link tests,
or the workflow itself after they reach `main`. It can also be run manually from the
Actions tab with `main` selected. Other branches cannot run the deployment job.

The build job runs the site tests and uploads **only `site/`** with
`actions/upload-pages-artifact`. The deployment job uses the `github-pages` environment,
`pages: write` and `id-token: write`. No personal access token or repository secret is
needed by the workflow. The repository must have Pages enabled and Actions permitted;
the environment must allow deployments from `main`.

The setup follows [GitHub's custom workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
No custom domain is configured. GitHub serves the project URL over HTTPS.

## Editing and verification

From the repository root:

```console
uv run python -m http.server 8088 --bind 127.0.0.1 --directory site
```

Open `http://127.0.0.1:8088`. Use relative asset paths so the site also works under the
`/TaxNorwayRAG/` project prefix. Update the research-status copy when its underlying
evaluation gates change. Run `uv run pytest tests/unit/test_pages.py --no-cov` to check
local assets, section anchors, linked repository files and the static research boundary.
The regular repository checks remain required. These tests do not evaluate models or
establish tax accuracy.

After merging, check the **GitHub Pages** Actions run and open the published URL.
To roll back, revert the site change on `main`; the workflow deploys the reverted content.

## Hosting boundary

GitHub Pages cannot run the Next.js server-side proxies, Python API, Qdrant or model
services. The working application keeps its existing private/local deployment described
in [frontend](frontend.md) and [three-machine deployment](three-machine-deployment.md).
The public page contains no query form and no connection to those services. Corpus data,
configuration files and the application source are excluded from the Pages artifact.
