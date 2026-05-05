# src/baseline_one_shot.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pywisim import EventLoop, Node, WirelessNetwork


class Stats:
    def __init__(self, n_participants):
        self.msg_sent = 0
        self.n_participants = n_participants
        self.received_count = 0
        self.last_receive_time = None
        self.completed = False
        self.finish_time = None

    def mark_received(self, t):
        self.received_count += 1
        self.last_receive_time = t
        if self.received_count == self.n_participants:
            self.completed = True
            self.finish_time = t


class Coordinator(Node):
    def __init__(self, nid, participants, stats):
        super().__init__(nid)
        self.participants = participants
        self.stats = stats

    def start(self):
        for p in self.participants:
            self.stats.msg_sent += 1
            self.unicast(p, ("COMMIT",))


class Participant(Node):
    def __init__(self, nid, stats):
        super().__init__(nid)
        self.stats = stats
        self.decision = None

    def on_receive(self, msg, sender):
        if msg[0] == "COMMIT" and self.decision is None:
            self.decision = "COMMIT"
            self.stats.mark_received(self.net.loop.time)


def run_baseline_trial(
    n_participants=3,
    loss=0.0,
    tx_range=1.5,
    seed=42,
    until=50.0,
    verbose=False,
    mobile=False,
    area=(8, 8),
    speed=0.0,
    pause=0.0,
):
    loop = EventLoop()
    net = WirelessNetwork(loop, tx_range=tx_range, loss=loss, seed=seed, verbose=verbose)
    stats = Stats(n_participants)

    participant_ids = [f"P{i+1}" for i in range(n_participants)]
    cx, cy = area[0] / 2, area[1] / 2
    net.add_node(Coordinator("C", participant_ids, stats), cx, cy)

    offsets = [(1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (-1, 1), (-1, -1), (1, -1)]
    for i, pid in enumerate(participant_ids):
        dx, dy = offsets[i % len(offsets)]
        net.add_node(Participant(pid, stats), cx + dx, cy + dy)

    if mobile and speed > 0:
        try:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from mobility import MobilityManager
            mover = MobilityManager(
                net, interval=1.0, speed=speed,
                bounds=(area[0], area[1]), fixed_nodes={"C"},
            )
            mover.start(model='waypoint')
        except Exception:
            pass

    loop.schedule(1.0, net.nodes["C"].start)
    loop.run(until=until)

    participant_decisions = {
        pid: getattr(net.nodes[pid], "decision", None) for pid in participant_ids
    }

    n_received = sum(1 for d in participant_decisions.values() if d is not None)
    unresolved = n_participants - n_received
    coordinator_decided = True  # baseline always issues commit at t=1
    completed = n_received == n_participants
    partial_delivery = 0 < n_received < n_participants

    decisions_received = [d for d in participant_decisions.values() if d is not None]
    atomicity_violation = len(set(decisions_received)) > 1
    consistent = (
        (len(set(decisions_received)) <= 1) and
        (not decisions_received or all(d == "COMMIT" for d in decisions_received))
    )

    return {
        "protocol": "ONE_SHOT",
        "n_participants": n_participants,
        "loss": loss,
        "seed": seed,
        "vote_yes_prob": 1.0,
        "mobile": mobile,
        "speed": speed if mobile else 0.0,
        "until": until,
        "coordinator_decided": coordinator_decided,
        "completed": completed,
        "partial_delivery": partial_delivery,
        "atomicity_violation": atomicity_violation,
        "consistent": consistent,
        "decision": "COMMIT",
        "finish_time": stats.finish_time,
        "msg_sent": stats.msg_sent,
        "unresolved_participants": unresolved,
        "all_participants_reached_decision": completed,
        **{f"{pid}_decision": d for pid, d in participant_decisions.items()},
    }
