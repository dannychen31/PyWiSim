import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pywisim import EventLoop, Node, WirelessNetwork

try:
    from mobility import MobilityManager
except Exception:
    MobilityManager = None


class Stats:
    def __init__(self):
        self.msg_sent = 0
        self.msg_received = 0
        self.completed = False
        self.decision = None
        self.finish_time = None
        self.prepare_retries = 0
        self.decision_retries = 0
        self.timeouts = 0

    def mark_finish(self, decision, t):
        if not self.completed:
            self.completed = True
            self.decision = decision
            self.finish_time = t


class RetryCoordinator(Node):
    def __init__(
        self,
        nid,
        participants,
        stats,
        vote_timeout=3.0,
        decision_timeout=3.0,
        max_prepare_retries=2,
        max_decision_retries=2,
    ):
        super().__init__(nid)
        self.participants = participants
        self.stats = stats
        self.vote_timeout = vote_timeout
        self.decision_timeout = decision_timeout
        self.max_prepare_retries = max_prepare_retries
        self.max_decision_retries = max_decision_retries

        self.votes = {}
        self.pending_decision_acks = set()
        self.decision = None
        self.prepare_round = 0
        self.decision_round = 0
        self.started = False

    def send_counted(self, dst, msg):
        self.stats.msg_sent += 1
        self.unicast(dst, msg)

    def start(self):
        if self.started:
            return
        self.started = True
        self.broadcast_prepare()
        self.net.loop.schedule(self.vote_timeout, self.on_vote_timeout)

    def broadcast_prepare(self):
        for p in self.participants:
            if p not in self.votes:
                self.send_counted(p, ("PREPARE", self.prepare_round))

    def on_vote_timeout(self):
        if self.decision is not None:
            return

        missing = [p for p in self.participants if p not in self.votes]
        if not missing:
            return

        self.stats.timeouts += 1
        if self.prepare_round < self.max_prepare_retries:
            self.prepare_round += 1
            self.stats.prepare_retries += 1
            self.broadcast_prepare()
            self.net.loop.schedule(self.vote_timeout, self.on_vote_timeout)
        else:
            self.decision = "ABORT"
            self.pending_decision_acks = set(self.participants)
            self.broadcast_decision()
            self.net.loop.schedule(self.decision_timeout, self.on_decision_timeout)

    def broadcast_decision(self):
        for p in list(self.pending_decision_acks):
            self.send_counted(p, ("DECISION", self.decision, self.decision_round))

    def on_decision_timeout(self):
        if not self.pending_decision_acks:
            return

        self.stats.timeouts += 1
        if self.decision_round < self.max_decision_retries:
            self.decision_round += 1
            self.stats.decision_retries += 1
            self.broadcast_decision()
            self.net.loop.schedule(self.decision_timeout, self.on_decision_timeout)

    def on_receive(self, msg, sender):
        self.stats.msg_received += 1
        kind = msg[0]

        if kind == "VOTE" and self.decision is None:
            _, vote, round_id = msg
            if sender not in self.votes:
                self.votes[sender] = vote

            if vote == "NO":
                self.decision = "ABORT"
                self.pending_decision_acks = set(self.participants)
                self.broadcast_decision()
                self.net.loop.schedule(self.decision_timeout, self.on_decision_timeout)
                return

            if len(self.votes) == len(self.participants):
                self.decision = "COMMIT"
                self.pending_decision_acks = set(self.participants)
                self.broadcast_decision()
                self.net.loop.schedule(self.decision_timeout, self.on_decision_timeout)

        elif kind == "ACK_DECISION":
            _, decision, round_id = msg
            if decision == self.decision and sender in self.pending_decision_acks:
                self.pending_decision_acks.remove(sender)
                if not self.pending_decision_acks:
                    self.stats.mark_finish(self.decision, self.net.loop.time)


class RetryParticipant(Node):
    def __init__(self, nid, vote_yes=True, stats=None):
        super().__init__(nid)
        self.vote_yes = vote_yes
        self.stats = stats
        self.decision = None
        self.last_prepare_round = None
        self.last_decision_round = None

    def send_counted(self, dst, msg):
        if self.stats is not None:
            self.stats.msg_sent += 1
        self.unicast(dst, msg)

    def on_receive(self, msg, sender):
        if self.stats is not None:
            self.stats.msg_received += 1

        kind = msg[0]

        if kind == "PREPARE":
            _, round_id = msg
            if self.last_prepare_round == round_id:
                return
            self.last_prepare_round = round_id
            vote = "YES" if self.vote_yes else "NO"
            self.send_counted(sender, ("VOTE", vote, round_id))

        elif kind == "DECISION":
            _, decision, round_id = msg
            if self.last_decision_round == round_id and self.decision == decision:
                return
            self.last_decision_round = round_id
            self.decision = decision
            self.send_counted(sender, ("ACK_DECISION", decision, round_id))


def _positions(n, radius=1.0):
    pts = [
        (1, 0), (0, 1), (-1, 0), (0, -1),
        (1, 1), (-1, 1), (-1, -1), (1, -1),
        (2, 0), (0, 2), (-2, 0), (0, -2)
    ]
    out = []
    for i in range(n):
        x, y = pts[i % len(pts)]
        out.append((x * radius, y * radius))
    return out


def run_tpc_retry_trial(
    n_participants=3,
    loss=0.0,
    tx_range=1.5,
    seed=42,
    vote_yes_prob=1.0,
    until=80.0,
    verbose=False,
    mobile=False,
    area=(8, 8),
    speed=0.0,
    pause=0.0,
    vote_timeout=3.0,
    decision_timeout=3.0,
    max_prepare_retries=2,
    max_decision_retries=2,
):
    loop = EventLoop()
    net = WirelessNetwork(loop, tx_range=tx_range, loss=loss, seed=seed, verbose=verbose)
    stats = Stats()

    participant_ids = [f"P{i+1}" for i in range(n_participants)]
    coord = RetryCoordinator(
        "C",
        participant_ids,
        stats,
        vote_timeout=vote_timeout,
        decision_timeout=decision_timeout,
        max_prepare_retries=max_prepare_retries,
        max_decision_retries=max_decision_retries,
    )
    cx, cy = area[0] / 2, area[1] / 2
    net.add_node(coord, cx, cy)

    for i, pid in enumerate(participant_ids):
        dx, dy = _positions(n_participants)[i]
        vote_yes = ((seed * 131 + i * 17) % 1000) / 1000.0 < vote_yes_prob
        net.add_node(RetryParticipant(pid, vote_yes=vote_yes, stats=stats), cx + dx, cy + dy)

    if mobile and speed > 0 and MobilityManager is not None:
        mover = MobilityManager(
            net, interval=1.0, speed=speed,
            bounds=(area[0], area[1]), fixed_nodes={"C"},
        )
        mover.start(model='waypoint')

    loop.schedule(1.0, net.nodes["C"].start)
    loop.run(until=until)

    participant_decisions = {pid: getattr(net.nodes[pid], "decision", None) for pid in participant_ids}

    n_received = sum(1 for d in participant_decisions.values() if d is not None)
    unresolved = n_participants - n_received
    coordinator_decided = stats.decision is not None

    completed = coordinator_decided and (n_received == n_participants)
    partial_delivery = coordinator_decided and (0 < n_received < n_participants)

    decisions_received = [d for d in participant_decisions.values() if d is not None]
    atomicity_violation = len(set(decisions_received)) > 1
    consistent = (
        (len(set(decisions_received)) <= 1) and
        (not decisions_received or all(d == stats.decision for d in decisions_received))
    )

    return {
        "protocol": "2PC_RETRY",
        "n_participants": n_participants,
        "loss": loss,
        "seed": seed,
        "vote_yes_prob": vote_yes_prob,
        "mobile": mobile,
        "speed": speed if mobile else 0.0,
        "until": until,
        "coordinator_decided": coordinator_decided,
        "completed": completed,
        "partial_delivery": partial_delivery,
        "atomicity_violation": atomicity_violation,
        "consistent": consistent,
        "decision": stats.decision,
        "finish_time": stats.finish_time,
        "msg_sent": stats.msg_sent,
        "msg_received": stats.msg_received,
        "prepare_retries": stats.prepare_retries,
        "decision_retries": stats.decision_retries,
        "timeouts": stats.timeouts,
        "unresolved_participants": unresolved,
        "all_participants_reached_decision": completed,
        **{f"{pid}_decision": d for pid, d in participant_decisions.items()},
    }