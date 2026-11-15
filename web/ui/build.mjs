import {readFile} from "node:fs/promises";
import {isAbsolute, join} from "node:path";
import {build} from "esbuild";
import {micromark} from "micromark";
import {slideRulesCss} from "./node_modules/@astryxdesign/core/dist/Layer/layerSlideRules.js";

const pagesOutput = process.env.PAGES_OUTPUT_DIR;
if (pagesOutput && !isAbsolute(pagesOutput)) throw new Error("PAGES_OUTPUT_DIR must be an absolute path");

// Include the pinned Astryx version's overlay positioning rules in the
// stylesheet so its popup runtime does not need to inject an inline style.
await build({
  entryPoints: ["app.jsx"],
  bundle: true,
  minify: true,
  outfile: pagesOutput ? join(pagesOutput, "app.js") : "dist/app.js",
  define: {STATIC_REPLAY_BUILD: JSON.stringify(Boolean(pagesOutput))},
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
