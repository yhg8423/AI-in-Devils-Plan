"""Build the static spectator site and replay files for Cloudflare Pages."""

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from .spectator import ASSETS, PLAY_RESULTS, UI, case_catalog, find_matches, next_match, read_match


OUTPUT = UI / "dist" / "pages"


def write_json(path: Path, data: object) -> None:
    with path.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, separators=(",", ":"))


def write_replays(replay_dir: Path) -> None:
    replay_dir.mkdir()
    write_json(replay_dir / "cases.json", case_catalog(PLAY_RESULTS))
    logs = find_matches(PLAY_RESULTS)
    for run_id, log in logs.items():
        run_dir = replay_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        for language in ("ko", "en"):
            match = read_match(log, language=language)
            if match.get("format") == "match" and match["complete"]:
                match["next_match"] = next_match(PLAY_RESULTS, logs, run_id)
            write_json(run_dir / f"{language}.json", match)


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=OUTPUT.parent) as temp:
        staged = Path(temp) / "pages"
        staged.mkdir()
        subprocess.run(
            ["npm", "run", "build"],
            cwd=UI,
            env={**os.environ, "PAGES_OUTPUT_DIR": str(staged)},
            check=True,
        )
        index, _ = ASSETS["/"]
        html = (UI / index).read_text(encoding="utf-8")
        # Browsers may cache JS and CSS across Pages deployments.
        for name in ("app.css", "app.js"):
            version = sha256((staged / name).read_bytes()).hexdigest()[:12]
            html = html.replace(f'="/{name}"', f'="/{name}?v={version}"')
        (staged / index).write_text(html, encoding="utf-8")
        # A root 404 disables the SPA fallback for unknown replay JSON paths.
        (staged / "404.html").write_text(html, encoding="utf-8")
        (staged / "_headers").write_text(
            "/*\n"
            "  Content-Security-Policy: default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; object-src 'none'\n"
            "  X-Content-Type-Options: nosniff\n",
            encoding="utf-8",
        )
        for url in ASSETS:
            if url != "/" and not (staged / url[1:]).is_file():
                raise FileNotFoundError(f"Missing build asset: {url}")
        write_replays(staged / "replays")
        if OUTPUT.exists():
            shutil.rmtree(OUTPUT)
        staged.rename(OUTPUT)
    print(f"Pages site built at {OUTPUT}")


if __name__ == "__main__":
    main()
