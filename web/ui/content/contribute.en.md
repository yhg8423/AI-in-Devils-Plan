# Contribute

You can help document the show's rules, report problems in the simulation, implement a new match, propose experiments comparing how AI agents play, or improve the website and documentation.

## Report a rule or bug

Let us know if a rule is missing or differs from the show, or if you encounter a bug in the simulation or on the website.

- **For a rule report**, include the episode, the timestamp, and the rule that is missing or implemented differently.
- **For a bug report**, describe what you were doing and what happened. If the problem occurred in a replay, include its URL and event number. A screenshot and your device or browser details can also help.

## Propose a feature or experiment, or try one yourself

For website features, tell us where you wanted the feature and which information you would like to find or compare more easily. If you have implemented it, share what changed on the page or in the interaction.

You can run the same match with different models, player personas, or information-sharing rules. When proposing an experiment, describe what you would change and which behaviors or results you would compare.

If you [ran the experiment yourself](https://github.com/yhg8423/AI-in-Devils-Plan/blob/main/README.en.md#run-locally), compress the `events.jsonl` result into a ZIP file and attach it to a GitHub issue. Include your settings and the differences you observed.

## Contribute code, tests, or documentation

- **Match implementation and tests** live in `games/`. You can implement rules for a new match, what players can see and do, and how the results are decided. You can also refine existing rules or test tie-breaking, delivery of private information, and when the next match starts.
- **The website and replay features** live in `web/ui/`. You can improve the mobile layout, keyboard controls, or how match logs are displayed.
- **Documentation and page content** live in the Korean and English READMEs and in `web/ui/content/`. You can clarify commands and game rules or edit the About, How it works, and Contribute pages.

Look for related issues first and leave a comment if a rule or the scope of a feature needs discussion. Follow the [contribution guide](https://github.com/yhg8423/AI-in-Devils-Plan/blob/main/CONTRIBUTING.md#contributing-in-english) to fork the repository on GitHub, clone your fork locally, and make your changes on a working branch. Verify your changes, push the branch to your fork, and [open a pull request](https://github.com/yhg8423/AI-in-Devils-Plan/pulls) against `main` in the original repository.

In the pull request, describe what changed and how you checked it. For a rule change, include the relevant scene from the show and your verification results. For a website change, include the page or replay position you checked.

---

[Browse GitHub issues](https://github.com/yhg8423/AI-in-Devils-Plan/issues)
