# Reader Simulator in the browser

The same reader simulator as the Windows app, compiled to WebAssembly, so nothing needs installing:
<https://pewpewzxc.github.io/reader-simulator/>

- `site/` is the page. Its list of builds (`builds.json`) and the builds themselves are not in git: the
  **Web simulator (Pages)** workflow keeps them up to date by itself. Every Monday (or on "Run workflow") it looks up
  each firmware's newest releases (3 by default), builds the ones not on the page yet with Emscripten on Linux
  (`ci_build.py`), starts each in headless Chrome (`test_site.mjs`), puts the passing ones in a `web-builds-<date>`
  release, publishes the list to the `web-feed` release and deploys. `site/builds.json` in git is only the starting
  list for the first run.
- `../samples/sd-card/` is copied onto every new simulated SD card: two CC0 books and a WordNet dictionary of their
  words (`../samples/make_dictionary.py`), set as the reader's dictionary so hold / tap to look up work.
- Books and the simulated SD card stay in your browser (IndexedDB); nothing is uploaded.
- Unofficial, not affiliated with Xteink. The simulator is an approximation of a real reader.

Builds are made with Emscripten from each firmware's public source plus the simulator library; see the
About page for credits and licences.
