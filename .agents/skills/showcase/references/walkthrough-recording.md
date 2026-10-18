# Recording a walkthrough without the owner

This is how the Compute Cost & Risk Monitor walkthrough was recorded: a Streamlit dashboard,
1:58 long, at 1920 × 1080, with captions. `record-walkthrough.example.mjs` is the script that
recorded it. Copy it and change the steps.

## Serve the app safely

- **Serve only demo data.** Use a launcher that offers only the synthetic database.
- **Bind to 127.0.0.1.** Streamlit reads `.streamlit/config.toml` from beside the app script or
  the current folder. A launcher kept elsewhere loses that config and listens on the whole
  network. Pass `--server.address 127.0.0.1` anyway.
- **Confirm the binding:** `netstat -ano | grep LISTENING | grep :PORT` must show
  `127.0.0.1:PORT`.
- **Stop the app** when the recording is done.

## Drive a headless browser

- Start Edge or Chrome with `--headless=new --remote-debugging-port=N --user-data-dir=<scratch>`,
  and talk to it over the DevTools protocol with Node's built-in `WebSocket`.
- Set `Emulation.setDeviceMetricsOverride` to 1920 × 1080.
- **Inject an overlay** into the page, outside the app's root element:
  - a caption bar;
  - a highlight box, which dims the rest of the page with a wide box-shadow;
  - a pointer arrow;
  - a full-screen panel for the title card, the end card and documents.
- **Give the overlays z-index values from about 2147483000.** App sidebars sit above lower
  values and hide the overlay.
- **Find targets by their text** with a TreeWalker over text nodes:
  - match case-insensitively, since labels are often uppercased with CSS;
  - treat every kind of space alike, since NBSP and thin spaces break exact matches;
  - limit the search to the main panel when the sidebar repeats the text.
- **Canvas tables** (`st.dataframe`) have no text to find. Target their container instead,
  counting only visible elements: hidden tabs keep zero-size copies in the page.
- **Escape backslashes inside the injected script.** In a JS template literal, `/\s/` becomes
  `/s/` unless you write `\\s`.
- **Click** by moving the fake pointer to the target's centre, then sending
  `Input.dispatchMouseEvent` (moved, pressed, released).
- **Type** with `Input.insertText`, one character at a time, then send an Enter key event.

## Capture and assemble

- **Capture** with `Page.startScreencast` (JPEG, quality 90). Acknowledge every frame, and note
  each frame's arrival time.
- **Assemble at a constant 30 fps:** for each tick, hard-link the latest frame into
  `seq/%06d.jpg`, then run:

  ```sh
  ffmpeg -framerate 30 -i seq/%06d.jpg -vf format=yuv420p -c:v libx264 -crf 20 -preset slow -movflags +faststart out.mp4
  ```
- **Don't use the concat demuxer** with per-frame durations. It pads frames shorter than
  1/25 s, so the video drifts and runs long.
- **Caption timing:** hold each caption for max(3.6 s, words ÷ 2.5 + 1.4 s).
- **Measure the real caption times** for the script table. Crop the caption area, convert it to
  small grey raw frames at 5 fps, and mark where the mean pixel difference jumps.
  `select='gt(scene,…)'` is too coarse for text changes.

## Working habits

- Write long scripts to files and run them. Long heredocs mangle backslashes.
- Do a preview pass of stills, tile four of them into one image with `xstack`, and look at it
  before recording.
- Keep the MP4 out of Git until the owner decides where it goes.
