# How the simulation works

A Python game engine runs the matches and saves a log that you can replay in your browser. This page covers what the agents see, how they submit actions, what carries over from one match to the next, and how the replays work.

## 1. What libraries and references does the project use?

The simulation is written in Python. [Concordia](https://github.com/google-deepmind/concordia) handles each player's observations and action requests, and [ChatArena](https://github.com/Farama-Foundation/ChatArena) manages conversations and private messages. The website uses [React](https://react.dev/) and [Astryx](https://astryx.atmeta.com/) for controls such as playback buttons and tabs. The pixel-art sets and characters are drawn using the browser's Canvas API.

The game rules come from Season 3 and episode-by-episode rule summaries. The sets and Pieces draw on the [official Netflix trailer](https://about.netflix.com/en/news/the-devils-plan-dead-again-main-trailer). The way the replays show characters moving and speaking in a shared space was inspired by [Generative Agents (Park et al., 2023)](https://hci.stanford.edu/publications/paper.php?id=482).

## 2. How do the agents interact with the game engine?

Either/Or, Heavy 13, Mystery Stock Exchange, and Russian Roulette each have their own Python module. The shared `Match` runner requests and records actions. The individual modules calculate Victory Points, penalties, trades, and final standings.

ChatArena's `MessagePool` filters the messages each player can see. Concordia keeps a separate agent and observation memory for each player and asks the model for its next action based on what that player has seen and what they are trying to achieve. Lay the Grass also uses ChatArena's `Arena` and `Environment` to run turns and tile placements.

## 3. How are models called and their responses handled?

The same agent code supports the Codex CLI, OpenAI Responses API, Claude Code, and Claude API. You can specify a model for text and another for requests with images. For example, the default model can handle negotiations while an image model receives the four views used in Cube Counting.

Models respond in JSON. For Choice 1 in Either/Or, an agent submits both a choice and a reason, such as `{"action":"보험금","note":"감옥동에 갈 가능성이 높다고 봤습니다."}`. Here the agent chooses insurance because it expects to go to the Prison Wing. The engine checks the rules for that point in the game, such as whether a player actually holds the submitted card or whether a tile overlaps an occupied space. If an action is invalid, the shared runner logs it privately and uses the fallback action for that phase.

## 4. How do players receive different information?

Each event's `visible_to` field records whether it is public or who can see it. When asking for an action, the engine sends the player ID, persona, objective, current rules and choices, and the recent events and conversations that player can see. This is how Either/Or shows the rules for Choices 6–8 early to the players who chose information in Choice 5.

The engine tracks player movements in the main hall, including the hallway and the four rooms. Room messages reach the players who are present when they are sent. A whisper can go to one other player in the same location. Room invitations tell recipients what the discussion is about, and accepting an invitation moves the recipient into that room.

## 5. How does the engine handle simultaneous and sequential actions?

For terminal votes and card-and-chip submissions in Heavy 13, the engine holds the game state fixed and requests responses in parallel. Players decide at the same point in the game, with the information available to each of them. They cannot see each other's current submissions. Once any additional review is complete, the engine collects the final responses and reveals what the rules allow.

In Lay the Grass, the board updates after each tile placement so the next player sees the new position. Mystery Stock Exchange divides each round into five simulated minutes, with one opportunity to act per player per minute. Players can place orders on turns when they also speak or move. A filled order immediately updates cash and holdings.

## 6. How are strategy notes and additional reviews recorded?

A strategy note is a short explanation submitted alongside a player's action. In phases that allow additional review, the model can submit a provisional answer and say what it wants to reconsider. The engine makes one more call when the provisional answer is valid and uses the revised answer if it is valid too. For simultaneous decisions handled by the shared runner, an invalid revision leaves the provisional answer in place.

In one Mystery Stock Exchange run, players coordinated their orders because they thought the amount they **bought** would trigger a price increase for Huja Electronics. The trigger depended on total **holdings**. Select a player in the replay and compare their notes under **Thoughts and Reviews** with their orders under **Conversations and Actions** to see how their hypothesis differed from the clue revealed later.

## 7. What carries over from earlier matches?

When running linked matches, the engine reads completed `events.jsonl` logs to carry over the surviving players and their Pieces. A prison match starts with the Prison Wing roster from the preceding main match. The Day 2 main match reads both results from Day 1 and excludes anyone eliminated in either match. The same player ID loads the same persona again.

The engine carries forward the latest affinity and trust scores for each pair of players, keeping the two directions separate. For example, P01's scores for P02 are stored separately from P02's scores for P01. During the next match, players can update their scores based on conversations and actions they have seen. Mystery Stock Exchange offers a review every four rounds, and later model requests include those updates.

## 8. How does replaying a saved match work?

The engine appends one line to `events.jsonl` whenever a player speaks, moves, makes a choice, or changes the score. The Python web server sends only fully written lines to the browser. React applies events in order up to the selected point, restoring the game state and player positions, and draws the set using Canvas. The browser checks the log periodically to follow a match that is still running.

Use **Jump to section** to skip to a moment such as a rule reveal or the start of a negotiation. The perspective control changes which events you see. The operator view shows all events, the public view shows those everyone saw, and a player's view shows what that player could see.

---

[Watch match replays](/#matches)
