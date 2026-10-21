"""The web app's view of the sectioning core.

The core lives in the `section-anything` package (packages/section-anything). Modules here
re-export it under the app's old import paths and inject the app's settings
(`app.core.config.Settings.sectioning_settings`). Only `jobs.py` (database, progress, audit) and
the browser-bridge registry belong to the app itself.
"""
