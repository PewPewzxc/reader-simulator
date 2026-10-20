# Reader Simulator in the browser

The same reader simulator as the Windows app, compiled to WebAssembly, so nothing needs installing:
<https://pewpewzxc.github.io/reader-simulator/>

- `site/` is the page. `site/builds.json` lists every build (firmware, version, device, SHA-256 of its files).
- The big files of each build (`sim.js`, `sim.wasm`) are assets of the GitHub release named in `builds.json`,
  not in git. `.github/workflows/pages.yml` downloads them, checks their SHA-256 and publishes the site.
- Books and the simulated SD card stay in your browser (IndexedDB); nothing is uploaded.
- Unofficial, not affiliated with Xteink. The simulator is an approximation of a real reader.

Builds are made with Emscripten from each firmware's public source plus the simulator library; see the
About page for credits and licences.
