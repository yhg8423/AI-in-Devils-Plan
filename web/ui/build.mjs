import {readFile} from "node:fs/promises";
import {build} from "esbuild";
import {micromark} from "micromark";
import {slideRulesCss} from "./node_modules/@astryxdesign/core/dist/Layer/layerSlideRules.js";

// Include the pinned Astryx version's overlay positioning rules in the
// stylesheet so its popup runtime does not need to inject an inline style.
await build({
  entryPoints: ["app.jsx"],
  bundle: true,
  minify: true,
  outfile: "dist/app.js",
  loader: {".woff2": "file"},
  plugins: [{
    name: "info-markdown",
    setup(build) {
      build.onLoad({filter: /\.md$/}, async ({path}) => ({
        contents: micromark(await readFile(path, "utf8"), {
          allowDangerousHtml: false,
          allowDangerousProtocol: false,
        }),
        loader: "text",
      }));
    },
  }],
  assetNames: "[name]",
  footer: {css: slideRulesCss()},
});
