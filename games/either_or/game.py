"""Day 1 main match, from Choice 1 through final residency and pieces."""

from ..match import Decision, Match
from .cube_counting import cube_priority
from .lay_the_grass.choice_five import CHOICE_REQUEST
from .lay_the_grass.demo import DEMO_DISCUSSION_ROUNDS, make_grass_arena
from .lay_the_grass.environment import PHASE_LABELS, LayTheGrass
from .lay_the_grass.live import LiveGrassBackend
from .lay_the_grass.simulation import gather_arena_actions, play_arena
from .memory_poker import memory_stage
from .negotiation import negotiate
from .rectangle_counting import rectangle_stage


class LimitedGrassBackend(LiveGrassBackend):
    def __init__(self, name, game, match, scripted):
        self.match = match
        self.previous = match.observations(name)
        self.scripted = scripted
        super().__init__(name, match.models[name], game, allow_review=match.allow_review, reserve_review=match.take_model_turn,
                         relationships=match.relationships[name])

    def query(self, agent_name, role_desc, history_messages, global_prompt=None, request_msg=None):
        self.last_decision_note = ""
        if self.match.take_model_turn():
            action = super().query(agent_name, role_desc, [*self.previous, *history_messages], global_prompt, request_msg)
            if self.invalid_action is None:
                return action
        return self.scripted.query(agent_name, role_desc, history_messages, global_prompt, request_msg)


def play(match: Match) -> dict:
    players = match.players
    scores = dict.fromkeys(players, 0)
    pieces = match.pieces.copy()
    match.event("rules", "양자택일 · 게임 규칙\n"
                "참가자 16명이 열 가지 선택과 네 미니게임을 진행합니다. 개인 단말기에 공개되는 선택에 답하고, "
                "각 미니게임과 선택 결과에 따라 누적 승점이 바뀝니다. 승점은 0점에서 시작하며, 변동이 생기면 "
                "전원의 승점을 공개합니다. 기본 시작 피스는 각 1개입니다.\n"
                "종료 후 1~6위는 생활동, 7~14위는 감옥동에 배정되며, 기본 탈락 인원은 최하위 2명입니다. "
                "최종 1위는 연맹의 징표로 감옥동 예정자 한 명을 생활동으로 옮길 수 있습니다.")
    match.event("rules", "선택 1 · 성과금 / 보험금\n"
                "성과금은 최종 생활동 배정 시 피스 1개, 보험금은 최종 감옥동 배정 시 피스 2개를 줍니다. "
                "게임이 끝나고 연맹의 징표까지 적용한 최종 배정으로 정산합니다.")
    bonus = match.decide_together("choice_1", {
        name: Decision("생활동 진출 시 피스 1개를 주는 성과금, 감옥동 배정 시 피스 2개를 주는 보험금 중 고르세요.",
                       match.policy.choice(("성과금", "보험금")), options=("성과금", "보험금")) for name in players
    })
    priority = cube_priority(match)
    rectangle_stage(match, priority, scores, pieces)
    match.event("rules", "선택 4 · 공공의 이익 / 개인의 이익\n"
                "공공의 이익은 16명 중 9명 이상이 골라야 상금의 징표를 획득합니다. "
                "징표 하나는 시즌 우승 상금 1억 원에 해당하며, 이 게임에서는 획득 여부를 기록합니다. "
                "개인의 이익은 다른 참가자의 선택과 관계없이 고른 사람만 승점 5점을 받습니다.")
    negotiate(match, 4, "선택 4를 투표하기 전입니다. 공공의 이익에 필요한 9표를 모을 수 있는지, "
              "개인의 이익으로 얻는 5점이 내 순위와 생존에 어떤 영향을 주는지 비교하세요.", players[:3], (
                  "공공 쪽으로 9표를 모을 수 있을까요? 우선 가까운 사람부터 의향을 물어봐요.",
                  "9표가 될 것 같으면 공공을 검토할게요. 그 전에는 5점을 포기하기 어려워요.",
                  "제 순위에는 5점이 필요해요. 공공에 투표하겠다고 약속하기는 어려워요.",
              ))
    votes = match.decide_together("choice_4", {
        name: Decision("공공의 이익을 9명 이상 고르면 상금의 징표를 획득합니다. 개인의 이익을 고르면 나만 승점 +5입니다.",
                       "개인" if match.policy.random() < 0.5 else "공공", options=("공공", "개인")) for name in players
    })
    prize = sum(vote == "공공" for vote in votes.values()) >= 9
    for name, vote in votes.items():
        scores[name] += 5 if vote == "개인" else 0
    match.event("choice_4_result", {"choices": votes, "prize_token": prize})
    match.event("scoreboard", scores)
    match.review_relationships("선택 4 투표 공개")

    match.event("rules", CHOICE_REQUEST + "\n"
                "방송은 정보 미리보기에 5분, 이후 게임 시작까지 20분을 주었습니다. "
                f"시뮬레이션은 선택 5 전후로 각각 {DEMO_DISCUSSION_ROUNDS}턴 협상하며, "
                "정보를 받은 참가자는 두 번째 협상 전에 비공개 계획을 한 번 작성합니다.")
    grass = LayTheGrass(scores, priority, discussion_rounds=DEMO_DISCUSSION_ROUNDS)

    def wrap_backend(name, scripted):
        if name in match.backends and match.live_turns:
            return LimitedGrassBackend(name, grass, match, scripted)
        return scripted

    def gather_actions(arena, names, *, simultaneous):
        backends = {name: arena.name_to_player[name].backend for name in names
                    if isinstance(arena.name_to_player[name].backend, LimitedGrassBackend)}

        def gather():
            return gather_arena_actions(arena, names, simultaneous=simultaneous)

        if not backends or not match.live_turns:
            return gather()

        def decide():
            actions = gather()
            return {"actions": actions, "invalid": {name: backend.invalid_action for name, backend in backends.items()}}

        saved = match.decision(["grass", grass.phase, len(match.events), list(names)], decide)
        for name, backend in backends.items():
            backend.invalid_action = saved["invalid"][name]
            backend.last_decision_note = saved["actions"][name][1]
        return saved["actions"]

    recorded = 0

    def copy_grass_events():
        nonlocal recorded
        checkpoint = None
        for event in grass.match_events(recorded):
            match.event(event.msg_type, event.content, actor=event.agent_name,
                        private=() if event.visible_to == "all" else event.visible_to)
            recorded += 1
            if event.msg_type == "choice_request":
                checkpoint = "선택 5 전 협상 종료"
            elif event.msg_type == "grass_phase" and event.content == PHASE_LABELS["draft"]:
                checkpoint = "잔디 깔기 배치 전 협상 종료"
        if checkpoint:
            match.review_relationships(checkpoint)

    arena = make_grass_arena(grass, wrap_backend=wrap_backend)
    copy_grass_events()
    play_arena(arena, after_step=copy_grass_events, gather_actions=gather_actions)
    if not grass.is_terminal():
        raise RuntimeError("Lay the Grass ended before scoring")
    scores = grass.scores
    ranking = sorted(players, key=lambda name: (-scores[name], priority.index(name)))
    match.event("pre_poker_ranking", {"ranking": ranking, "pieces": pieces})
    match.review_relationships("잔디 깔기 결과")
    match.event("rules", "선택 9 · 탈락 인원 1명 / 2명\n"
                "피스 8개를 함께 지불하면 최하위 1명만 탈락합니다. 모으지 못하면 최하위 2명이 탈락합니다. "
                "모금이 성립하면 징표 사용 전 1~7위는 생활동, 8~15위는 감옥동 예정입니다. "
                "어느 경우든 연맹의 징표 사용 후 감옥동에는 7명이 남습니다. "
                "시뮬레이션에서는 각자 보유량과 8개 중 작은 수까지 비공개로 약정합니다. 합계가 8개 이상이면 "
                "현재 순위가 높은 참가자부터 약정한 한도에서 총 8개만 지불합니다. 8개 미만이면 누구도 지불하지 않습니다.")
    speakers = tuple(name for name in players if name in ranking[-3:])
    negotiate(match, 9, "선택 9를 제출하기 전입니다. 총 8피스를 모을 수 있는지, "
              "각자가 얼마를 부담할지, 탈락을 한 명으로 줄이면 누가 이득을 얻는지 논의하세요. "
              "피스는 협상 뒤 각자의 비공개 약정으로 확정합니다.", speakers, (
                  "탈락을 한 명으로 줄이려면 총 8피스가 필요해요. 각자 낼 수 있는 개수를 맞춰볼까요?",
                  "하위권만으로는 부족할 수 있어요. 낼 의향이 있는 사람을 더 찾아야 해요.",
                  "제 몫은 보유한 피스 안에서 검토할게요. 다른 사람이 내겠다고 한 만큼도 확인해 주세요.",
              ))
    decisions = {}
    for name in ranking:
        maximum = min(8, pieces[name])
        decisions[name] = Decision("총 피스 8개를 모으면 탈락을 2명에서 1명으로 줄이고 생활동 기본 배정을 7명으로 늘립니다. "
                                   f"합의가 성립할 때 낼 내 피스 개수(0~{maximum})를 고르세요.",
                                   str(maximum if name in ranking[-2:] else 0),
                                   options=tuple(str(n) for n in range(maximum + 1)))
    pledges = {name: int(action) for name, action in match.decide_together("choice_9", decisions).items()}
    elimination_count = 2
    if sum(pledges.values()) >= 8:
        elimination_count = 1
        remaining = 8
        for name, pledge in pledges.items():
            payment = min(remaining, pledge)
            pieces[name] -= payment
            remaining -= payment
    match.event("choice_9_result", {"pledged": sum(pledges.values()), "eliminations": elimination_count})
    match.review_relationships("선택 9 모금 결과")
    memory_stage(match, ranking, pieces)

    living_count = 7 if elimination_count == 1 else 6
    match.event("rules", "최종 배정 · 연맹의 징표와 피스 정산\n"
                f"최종 1~{living_count}위는 생활동, 최하위 {elimination_count}명은 탈락입니다. 나머지는 감옥동 예정입니다. "
                "1위가 연맹의 징표로 감옥동 예정자 한 명을 생활동으로 옮긴 뒤, 최종 배정을 기준으로 "
                "선택 1의 성과금 또는 보험금을 지급합니다. 탈락자는 선택 1 보상을 받지 않으며 방송에서는 보유 피스를 반납합니다. "
                "실행 결과의 피스는 탈락 직전 잔고를 포함합니다.")
    living = ranking[:living_count]
    prison = ranking[living_count:-elimination_count]
    saved = match.decide(ranking[0], "alliance", f"최종 순위 {ranking}. 감옥동 예정 중 생활동으로 옮길 사람을 고르세요.",
                         prison[0], options=prison, private=False)
    living.append(saved)
    prison.remove(saved)
    for name, choice in bonus.items():
        if choice == "성과금" and name in living:
            pieces[name] += 1
        if choice == "보험금" and name in prison:
            pieces[name] += 2
    return {"ranking": ranking, "scores": scores, "priority": priority, "pieces": pieces,
            "living": living, "prison": prison, "eliminated": ranking[-elimination_count:],
            "alliance_saved": saved, "prize_token": prize, "grass_placements": len(grass.placed)}
