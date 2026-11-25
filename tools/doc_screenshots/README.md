# Doc screenshots (not shipped)

The live page's screenshots in `docs/images/live-*.png` and `tracking-snapshot-*.png`.
The screenshots of Blender itself (panels, dialogs) are made by hand.

## From a real project (2.0.0's)

A headless Blender serves the project's live page, and exports its snapshot; Playwright
(Python) screenshots both. Nothing is written in the project.

    X=tools/doc_screenshots; P=/path/to/demo; T=/tmp/shots
    mkdir -p $T/ext/user_default $T/snapshot && ln -sfn "$PWD" $T/ext/user_default/minimalist_pipeline
    BLENDER_USER_EXTENSIONS=$T/ext BLENDER_USER_CONFIG=$T/cfg blender -b --factory-startup --python $X/serve_project.py -- $P 1800 > $T/serve.log &
    OUT=$T/snapshot/demo_snapshot.html BLENDER_USER_EXTENSIONS=$T/ext BLENDER_USER_CONFIG=$T/cfg2 blender -b --factory-startup --python $X/export_snapshot.py -- $P
    python -m venv $T/venv && $T/venv/bin/pip install playwright && $T/venv/bin/playwright install chromium-headless-shell
    $T/venv/bin/python $X/shoot_project.py "$(grep -o 'http[^ ]*' $T/serve.log)" $T/snapshot/demo_snapshot.html $T/shots parcel

Then resize `shots/*.png` into `docs/images/`: the desktop ones 1600 px wide, the phone
ones 1170.

## From the fixtures (1.x's way, no Blender)

The demo fixtures (`tests/fixtures/`), with a made-up 70-day history and a farm at work:
the page built by the fake bpy, served to Chromium by Playwright (Node).

    python3 tools/doc_screenshots/build_pages.py /tmp/shots/page.html
    python3 tools/doc_screenshots/build_pages.py /tmp/shots/live.html live
    cd /tmp/shots && mkdir -p shots && node /path/to/repo/tools/doc_screenshots/shoot.js
