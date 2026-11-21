# Doc screenshots (not shipped)

The live page's screenshots in `docs/images/live-*.png` and `tracking-snapshot-*.png`,
made from the demo fixtures (`tests/fixtures/`), with a made-up 70-day history and a few
machines with files open. No Blender needed: the page is built by the fake bpy, served to
Chromium by Playwright (`/data` held, so the page reads "up to date").

    python3 tools/doc_screenshots/build_pages.py /tmp/shots/page.html
    python3 tools/doc_screenshots/build_pages.py /tmp/shots/live.html live
    cd /tmp/shots && mkdir -p shots && node /path/to/repo/tools/doc_screenshots/shoot.js

Then copy `shots/*.png` into `docs/images/` (resized to 1600 px wide for the desktop ones).
The screenshots of Blender itself (panels, dialogs) are made by hand.
