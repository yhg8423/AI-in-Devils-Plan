# 기여하기

[English](#contributing-in-english)

방송 규칙의 오류를 제보하거나, 새 매치와 실험을 제안하거나, 코드와 문서를 개선할 수 있습니다.

## 제보와 제안

이미 같은 내용이 있는지 [GitHub 이슈](https://github.com/yhg8423/AI-in-Devils-Plan/issues)를 먼저 확인해 주세요.

- **규칙 제보**에는 방송 회차와 장면 시각, 방송의 규칙, 시뮬레이션이 적용한 규칙을 적어 주세요.
- **오류 제보**에는 재현 순서, 예상한 결과와 실제 결과를 적어 주세요. 재생 중이라면 페이지 주소와 기록 번호를, 실행 중이라면 명령과 오류 메시지를 함께 남겨 주세요.
- **기능이나 실험 제안**에는 바꾸려는 기능이나 실험 조건, 그 변화로 확인하고 싶은 행동이나 결과를 적어 주세요.

직접 실행한 결과를 공유할 때는 모델, 추론 수준, 시드 등 사용한 설정을 적고 `events.jsonl`을 ZIP으로 압축해 이슈에 첨부해 주세요. 로그와 설정에서 개인정보나 비밀값을 확인하고 가린 뒤 첨부해 주세요. `.env`와 API 키는 공유하지 마세요.

## 수정하고 확인하기

GitHub 저장소에서 **Fork**를 눌러 자신의 계정에 [포크를 만드세요](https://docs.github.com/en/pull-requests/how-tos/work-with-forks/fork-a-repo). 포크를 로컬에 복제한 뒤 `main`에서 작업 브랜치를 만들어 수정해 주세요.

게임 규칙과 테스트는 [`games/`](games/), 웹과 재생 화면은 [`web/`](web/)에서 찾을 수 있습니다. 프로젝트 문서는 [README](README.md)와 이 가이드에, 한국어·영어 웹 페이지의 본문은 [`web/ui/content/`](web/ui/content/)에 있습니다.

[README의 세팅 방법](README.md#세팅하기)을 따라 의존성을 설치한 뒤 저장소 루트에서 확인합니다. 아래 명령에는 API 키가 필요 없습니다.

```bash
uv run --locked --python 3.12 python -m unittest discover -v
npm --prefix web/ui run build
```

웹 동작을 바꿨다면 [로컬 웹 실행 방법](README.md#로컬에서-시작하기)을 따라 해당 화면이나 재생 위치에서 확인해 주세요.

## 풀 리퀘스트 보내기

수정 사항을 커밋하고 포크의 작업 브랜치에 푸시하세요. 그 브랜치에서 원본 저장소의 `main`을 대상으로 [풀 리퀘스트(PR)](https://github.com/yhg8423/AI-in-Devils-Plan/pulls)를 열어 주세요.

무엇을 왜 바꿨는지, 어떤 방법으로 확인했고 어떤 결과가 나왔는지 적어 주세요. 관련 이슈가 있다면 링크를 붙여 주세요. 규칙을 수정했다면 근거가 되는 방송 장면을, 웹을 수정했다면 확인한 페이지나 재생 위치를 함께 남겨 주세요.

## Contributing in English

You can report discrepancies in the game rules, propose new matches or experiments, or improve the code and documentation.

### Reports and proposals

Check [existing GitHub issues](https://github.com/yhg8423/AI-in-Devils-Plan/issues) for a similar report or proposal.

- **Rules.** Include the episode and timestamp, the rule shown in the broadcast, and how the simulation applies it.
- **Bugs.** Give the steps to reproduce the issue and describe what you expected and what happened. For replay issues, include the page URL and event number. For simulation issues, include the command and error message.
- **Features and experiments.** Describe the feature or experiment condition you want to change and the behavior or outcome you want to examine.

When sharing results from your own run, include settings such as the model, reasoning effort, and seed. Attach `events.jsonl` as a ZIP to the issue after removing personal information and secrets from the log and settings. Keep `.env` and API keys private.

### Make and verify changes

Select **Fork** on GitHub to [create a copy under your account](https://docs.github.com/en/pull-requests/how-tos/work-with-forks/fork-a-repo). Clone your fork locally and create a working branch from `main`.

Game rules and tests live in [`games/`](games/), and the website and replay interface are in [`web/`](web/). Project documentation is in the [README](README.en.md) and this guide. Korean and English website text is in [`web/ui/content/`](web/ui/content/).

Follow the [setup instructions](README.en.md#setup), then run these commands from the repository root. They require no API key.

```bash
uv run --locked --python 3.12 python -m unittest discover -v
npm --prefix web/ui run build
```

If you changed how the website works, [run it locally](README.en.md#run-locally) and check the affected page or replay position.

### Open a pull request

Commit your changes and push the branch to your fork. [Open a pull request](https://github.com/yhg8423/AI-in-Devils-Plan/pulls) from that branch targeting `main` in the original repository.

Explain what you changed, why you changed it, and how you verified it. Include the verification results and link any related issues. For a rules change, cite the relevant scene in the broadcast. For a website change, note the page or replay position you checked.
