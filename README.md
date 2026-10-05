# NBA Player Props Model

Standalone Streamlit baseline, created in an empty repository. The existing MLB application was not available, so this is not yet integrated with its navigation, database, or visual style.

## Run

```sh
cd /workspace/Sports_Data
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Run checks with `.venv/bin/python -m pytest -q`. SQLite snapshots, final box scores, and candidate training artifacts live in `data/nba.sqlite`. Back up this database. No live or sample data is bundled. No key is required for the page or normalized JSON workflow.

Optional provider environment variables: `BALLDONTLIE_API_KEY`, `SPORTSDATAIO_API_KEY`, `ODDS_API_KEY`. Set them securely in the runtime, never in source control. NBA.com via `nba_api` requires no key but can block cloud IPs. Network destinations: `api.balldontlie.io`, `api.sportsdata.io`, `api.the-odds-api.com`, `stats.nba.com`. Paid endpoint entitlements vary. Errors are surfaced without logging credential-bearing URLs.

## Data workflow

1. In Data Sources & Import, fetch a schedule and compatible game logs, or upload a normalized JSON bundle.
2. Verify roster membership (the initial schedule builder uses latest observed team), provide pregame injury/tracking context and map odds to explicit game/player IDs.
3. Inspect projections and missing inputs. Save the complete slate before tipoff. A snapshot is append-only and independent of later model changes.
4. Upload final box scores with `status: "Final"`. The audit joins exact player and game IDs to the saved projection; it never recalculates pregame predictions.
5. Review completed audits, snapshot replay backtests, ranking comparisons, and bias candidates in the retraining page.

### Normalized bundle contract

Top-level object: `players` array, `logs` array, optional `lines` array, optional `contexts` object keyed by player ID, and `source` string. Do not mix provider ID namespaces without an explicit mapping.

Each player: `player_id`, `player`, `team`, `opponent`, `game_id`, `game_time` (ISO UTC tipoff), optional `position`.

Each log: `player_id`, `date` (game timestamp), `min`, `pts`, `reb`, `ast`, `fg3m`, `stl`, `blk`; include `fg3a` for 3PM. Optional `season`, `known_at`, `fga`, `fgm`, `fta`, `ftm`, `pf`. `known_at` denotes when the observation became available. Historical inputs are strictly prior to the feature cutoff. Date-only logs are suitable only for previous calendar dates, not same-day reconstruction.

Each line: `player_id`, `game_id`, `stat` (`pts/reb/ast/fg3m/stl/blk`), `line`, `sportsbook`, `over_odds`, `under_odds`, `timestamp`, optional `opening_line`. Lines older than six hours cannot produce a recommendation. No historical lines are substituted from today's market.

Each context requires `known_at`. Supported fields include `projected_minutes`, `injury_status` (Available, Probable, Questionable, Doubtful, Out, Unknown), `{stat}_opportunity_score`, `{stat}_matchup_score`, `{stat}_matchup_adjustment`, `pace_adjustment`, `injury_adjustment`, `usage_adjustment`, `shot_volume_adjustment`, `free_throw_adjustment`, `rebound_chance_adjustment`, `opponent_misses_adjustment`, `frontcourt_role_adjustment`, `potential_assists_per_minute`, `assist_conversion`, `ball_handling_adjustment`, `teammate_shooting_adjustment`, `shot_quality_adjustment`, `opponent_turnover_adjustment`, `ball_handler_adjustment`, `rim_contest_adjustment`, `opponent_rim_adjustment`, `rim_role_adjustment`, `foul_adjustment`, `defensive_activity`, `three_volume_support`, `blowout_risk`, `rest_context`. Factors are bounded to 0.65–1.35. Scores are expected on 0–100 scales. Scores supplied in normalized imports must be backed by source observations; this baseline does not manufacture tracking scores from box scores.

Final results file: array of records with `game_id`, `player_id`, `status: "Final"`, `min`, and all six stat keys. Optional `observed_driver` supplies an evidence-based audit explanation. Otherwise the UI clearly marks automatic explanations as unconfirmed heuristics.

## Model behavior and limitations

Six separate formulas use season/recent per-minute rates and category-specific factors. Three-point projections separate attempts from a shrunk conversion rate (explicit 35% prior with 100 attempts); assists use potential assists and conversion when available. Missing adjustments are neutral, disclosed, and reduce confidence. Missing opportunity/matchup prevents betting recommendations and Top-3 scoring. Defensive stats have a conservative confidence cap and extra activity gates. Unknown or unresolved injury status prevents recommendations.

This is a baseline development implementation, not a finished validated predictive system. Confidence is a heuristic score, not an empirical probability. Advanced tracking ingestion, automatic opportunity/matchup feature engineering, robust current roster/injury integration, cross-provider odds entity resolution, automatic completed-game polling, injury lineup redistribution, production walk-forward model selection and held-out calibration remain to be implemented. SportsDataIO currently exposes raw provider imports, not normalized automatic fusion. No claims of betting profitability or predictive accuracy are made.

Retraining saves shrunk player/stat bias candidates; candidates are not automatically applied. Backtesting currently replays real saved pregame snapshots; it does not fabricate retrospective pregame snapshots. Leader capture covers the audited snapshot population, includes ties at the actual rank boundary, and cannot claim full-slate capture without a complete player population. Repeated snapshots and multiple books should be filtered before drawing performance conclusions.

The page includes slate summaries, props, ceiling/injury/role watchlists, audits, replay backtests, retraining diagnostics, and provider health. Empty datasets stay empty. Test fixtures are explicitly synthetic and confined to tests.

### Feature score inputs

`contexts[player_id].feature_percentiles[stat].opportunity` and `.matchup` accept source-derived 0–100 percentiles for the stat-specific features listed in `nba/features.py`. At least 70% of the documented feature weight must be observed to calculate a score. Missing metrics stay missing; score coverage is recorded. These percentile inputs must be computed from the pregame reference population. Precomputed scores remain supported for integration with an existing analytics pipeline. Category labels are included for confidence, role, opportunity, matchup, ceiling and Top-3 scores.

`known_at` on completed result records determines training eligibility. When omitted, the import timestamp is used conservatively. Candidate bias training deduplicates player/game/stat observations across books and snapshots.

### Schedule HTTP 403 fix

Build free NBA slate now falls back to BallDontLie's schedule endpoint when the NBA CDN request fails. It uses the existing BALLDONTLIE_API_KEY; it does not request paid game logs. NBA logs and player IDs remain unchanged. Exact, unique team abbreviations link schedule teams to the current NBA roster. Missing or ambiguous matches stop the build. BallDontLie game IDs are prefixed with `bdl:`; any later normalized result imports must use those same snapshot game IDs and NBA player IDs. Automatic cross-provider final-result mapping is not implemented. Schedule dates are filtered by UTC tipoff, with the prior calendar day included in the request for US evening games. No games or times are invented.

The free schedule fallback is covered by mocked tests, but live retrieval with your local key has not been verified from this workspace. An NBA HTTP 403 is described as a server denial, not a subscription requirement.

## Preseason schedule correction

The earlier October 5 'no games' diagnosis described BallDontLie's incomplete response, not the NBA schedule. ESPN's free scoreboard returns five October 5, 2026 preseason games. The app now uses that feed first, maps full team names to the live NBA roster without hardcoded team IDs, and groups games by America/New_York calendar date. UTC timestamps are still stored. The after-midnight UTC games stay in the Eastern evening slate.

The free build button imports baseline NBA logs automatically when none are cached. Preseason logs are requested separately using `Pre Season`; only completed prior-calendar-day preseason minutes can supply the preseason minutes estimate. Players without those observations remain N/A. Regular-season reference averages are explicitly separate from projected stats. Preseason confidence is capped below recommendation thresholds. Source availability is not evidence of forecast accuracy.

The app can now read named provider bindings and APP_ACCESS_PASSWORD from Streamlit's secrets settings as well as process environment variables. No credentials are included in source control. DEPLOYMENT.md describes the free Community Cloud and persistent paid-host options.

## Current validation

21 isolated automated tests pass. A live-data Streamlit check rendered all five October 5 preseason games, 206 roster players, and 1,236 stat rows, including late Eastern tipoffs. The feed had no prior preseason-minute observations for those players, so projections remained N/A rather than substituting regular-season workloads; regular-season averages were visible only as reference values. A regular-season October 20 check separately produced 390 numeric baseline projections. Neither check establishes predictive accuracy.

## Hosted NBA.com access fallback

Streamlit Community Cloud could start the app but could not retrieve NBA game logs. The app now prefers verified NBA snapshots when available, displaying their source and retrieval time. Bundled snapshots were fetched from NBA.com via nba_api, not generated. Current rosters, preseason logs and current-season regular logs expire after 24 hours; completed-season historical logs can remain available. Unavailable or stale data stays unavailable.

The Refresh real NBA snapshots workflow runs every six hours and can be dispatched manually. It publishes updated gzip snapshots to the `nba-data` branch, which the app reads over verified HTTPS. Data-only branch updates do not rebuild the deployed `main` app. A failed refresh preserves the prior snapshots and reports failure. Scheduled execution and provider availability are not guaranteed; source ages remain visible. This is separate from backing up the app's SQLite audit database.

## Automatic date imports

Choose a date in the sidebar on Player Props or Data Sources & Import. The app automatically loads its Eastern-date schedule, appropriate season history, current roster for upcoming dates, and preseason minutes when applicable. Configured BallDontLie injuries and The Odds API lines are imported automatically; exact player name, team pairing and tipoff must match before a prop is attached. Missing keys or optional endpoint failures remain visible without hiding players. SportsDataIO raw imports remain optional diagnostics, not a required part of the free workflow.

Each date has a separate 10-minute session cache and a dated cache file under data/slates. Changing filters does not repeat imports. Refresh selected date retries its imports. An empty date shows no games; a failed date never displays the previous date's slate. Previous cache versions and immutable SQLite pregame snapshots are preserved.

Past dates import the historical schedule and available final NBA box scores, matching both teams and the game date. They display original saved pregame predictions when present. They do not import current rosters, odds, or injuries, and never reconstruct pregame predictions from final box scores. Historical context that was never saved remains N/A.
