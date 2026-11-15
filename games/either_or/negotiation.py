"""Run Either/Or negotiations and collect optional early submissions."""

from ..match import encode
from .discussion import Discussion
from .lay_the_grass.choice_five_demo import DEMO_DISCUSSION_ROUNDS


def negotiate(match, choice, topic, speakers, dialogue, *, terminal_choices=None, submission_opens_on=1):
    rounds = DEMO_DISCUSSION_ROUNDS
    discussion = Discussion(match.players, rounds)
    phase = f"choice_{choice}_negotiation"
    host, guest, third = speakers
    proposal, reply, whisper = dialogue
    scripted = {
        (1, host): {"type": "move", "room": 1},
        (1, guest): {"type": "speak", "channel": "room", "room": 1, "text": proposal},
        (2, host): {"type": "speak", "channel": "room", "room": 1, "text": reply},
        (2, third): {"type": "speak", "channel": "whisper", "to": host, "text": whisper},
    }
    pass_action = {"type": "pass"}
    notes = dict.fromkeys(match.players, "들은 제안을 참고하고 선택 단계에서 내 계획을 제출한다.")
    submitted = {}
    start = {"choice": choice, "rounds": rounds, "topic": topic}
    if terminal_choices is not None:
        start["submission_opens_on"] = submission_opens_on
    match.event("negotiation_start", start)
    for round_number in range(1, rounds + 1):
        match.event("negotiation_round", {"choice": choice, "round": round_number})
        for seat, name in enumerate(match.players):
            turn = len(match.events)
            instructions = topic
            submission = None
            if terminal_choices is not None:
                if round_number < submission_opens_on:
                    instructions += (f"\n지금은 협상만 할 수 있습니다. 개인 또는 팀 선택은 {submission_opens_on}턴부터 "
                                     "비공개로 제출할 수 있습니다. 지금은 대화, 이동 또는 패스를 사용하세요.")
                elif name in submitted:
                    instructions += f"\n내 선택은 {submitted[name]}으로 확정했습니다. 남은 협상에서 대화하거나 이동할 수 있습니다."
                else:
                    submission = terminal_choices[name]
                    instructions += (
                        '\n지금 확정하려면 {"type":"submit","choice":"개인","note":"선택 근거"} 형식으로 '
                        "비공개 제출하세요. 제출은 한 번이며 수정할 수 없습니다. 더 논의하려면 협상 행동을 사용하세요.\n"
                        + submission.instructions()
                    )
                if round_number >= submission_opens_on:
                    instructions += f"\n선택 {choice} 제출 완료 {len(submitted)}/{len(match.players)}명."
            request = discussion.request(name, turn, instructions, action_index=(round_number - 1) * len(match.players) + seat,
                                         notes=True)
            default = pass_action if name in match.backends else scripted.get((round_number, name), pass_action)
            if default.get("channel") == "whisper" and discussion.location(name) != discussion.location(host):
                default = {**default, "room": discussion.location(host)}
            note = notes[name]
            if "text" in default:
                note = f"{default['text']} 상대가 실제 제출에서도 따를지 판단한다."

            def parse(action):
                return discussion.parse(name, action, turn, notes=True,
                                        validate_submission=submission.accepts if submission else None)

            def valid(action):
                try:
                    parse(action)
                except (ValueError, RecursionError):
                    return False
                return True

            action = match.request_action(name, phase, request.content, encode({**default, "note": note}),
                                          valid=valid, request_type=request.msg_type)
            decision = parse(action)
            notes[name] = decision.note
            for event in discussion.record(name, decision, turn):
                match.event(event.msg_type, event.content, actor=event.agent_name,
                            private=() if event.visible_to == "all" else event.visible_to)
            if decision.submission is not None:
                submitted[name] = decision.submission
                match.event("action", {"phase": f"choice_{choice}", "action": decision.submission},
                            private=[name], actor=name)
                match.event("choice_progress", {"choice": choice, "submitted": len(submitted), "total": len(match.players)})
                if len(submitted) == len(match.players):
                    match.event("negotiation_end", {"choice": choice, "reason": "all_submitted"})
                    return submitted
    end = {"choice": choice}
    if terminal_choices is not None:
        end["reason"] = "limit"
    match.event("negotiation_end", end)
    return submitted
