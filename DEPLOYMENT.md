# Public deployment preparation

The Docker image runs the Streamlit app on port 8501, as a non-root user. Credentials and local databases are excluded from the image. Set `NBA_DATA_DIR` to a persistent writable volume; otherwise audits disappear when the container is replaced. Do not copy cloud proxy credential placeholders to another machine.

`render.yaml` is a Render Blueprint for a paid Starter web service with a 1 GB persistent disk. It is preparation only: no hosting account, service, billing commitment or public URL has been created. Review current hosting costs before creating it. Connect the Git repository to Render and select this blueprint to deploy. Configure BALLDONTLIE_API_KEY securely on the host; NBA logs and rosters themselves require no key. Optional SportsDataIO and Odds API keys can be added later. The generated APP_ACCESS_PASSWORD protects the whole app, including import and database-write controls; obtain it privately from the host settings. Do not share API keys with visitors.

For another Docker host, build `docker build -t nba-props .`, expose port 8501 behind the host's HTTPS ingress, mount persistent storage at /app/data, and configure APP_ACCESS_PASSWORD plus any provider credentials as secrets. Keep XSRF/CORS defaults enabled. Localhost health is `/_stcore/health`; that checks the web server, not live provider readiness. Provider availability must be checked inside the app.

No-cost hosting may be suitable for viewing the app, but ephemeral disks do not meet durable audit/backtest storage requirements. This version uses SQLite and should run as one instance with one persistent volume. Back up the volume before changing hosts. The source repository must be pushed before a Git-based deployment; this task does not assume Git read access implies write access or a connected hosting account.

The local Windows copy is separate from this cloud checkout. Changes here cannot modify a Windows folder unless a local task is attached to it. No ZIP transfer is required or produced by this deployment preparation.

## Validation performed

The container was built and started as the non-root app user. Its health endpoint returned `ok`, SQLite integrity/write initialization passed, and the Streamlit page rendered in AppTest inside the container. The cloud Docker builder cannot reach package registries directly, so verification supplied the exact locked wheels downloaded with normal TLS verification through a temporary build context. The checked-in Dockerfile uses the ordinary pip install path for hosts with outbound build access. No credentials or user databases were included in the image. File ownership and proxy-independent loopback health checking were corrected during validation.

## Free Streamlit Community Cloud option

Sign in at https://share.streamlit.io with the GitHub account that can access Digital-Artisan-Co/Sports_Data. Create an app using branch `main` and entrypoint `app.py`; select Python 3.12. The root requirements.txt includes the tested dependency lock. The free ESPN schedule plus NBA.com logs/roster workflow does not need API keys. Other providers are optional. Set APP_ACCESS_PASSWORD privately in the app's Secrets settings to restrict access; optional named API keys are also read from Streamlit secrets. Never commit .streamlit/secrets.toml.

Use the app's Load schedule and player data button, then Build free NBA slate. That imports a baseline season if no logs are cached, loads the selected Eastern-date slate (including preseason), and joins current NBA roster IDs. For preseason, previous preseason minutes are used only if observed before the run; absent minutes remain N/A. Regular-season averages are labeled reference values, not preseason projections.

Free Community Cloud disk storage is not durable across app rebuilds or replacement. Download/export important pregame snapshots and audit data before redeploying. For retained SQLite audit history, use the persistent Render deployment described above. No Streamlit account connection or public app URL has been created by this task.
