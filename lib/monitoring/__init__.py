"""Monitoring: what the project says about itself, and where it's shown.

- tracking.py: tracking.json (notes, retakes, assignments) and the
  .stablemeta/.wipmeta read and written; status.py: a department's state
  from them; legacy.py: the 1.x keys still written beside 2.0's;
  schedule.py: the project's work days.
- snapshot.py: the project's data gathered for the page;
  snapshot_page.py: the page built from templates/snapshot;
  review_import.py: a review sent from the page applied; live.py: the page
  served by Blender (qr.py: its link as a QR code).
- windows.py: the monitoring windows in Blender (log, welcome, settings).

lib/__init__.py exports what the rest of the addon calls."""
