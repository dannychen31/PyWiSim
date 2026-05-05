import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
data_path = ROOT / "data" / "results.csv"
fig_dir = ROOT / "figures"
fig_dir.mkdir(exist_ok=True)

df = pd.read_csv(data_path)

for col in ["completed", "coordinator_decided", "partial_delivery", "atomicity_violation",
            "consistent", "all_participants_reached_decision"]:
    if col in df.columns:
        df[col] = df[col].fillna(False).astype(float)

# deadline-penalized latency: use finish_time if completed, else simulation deadline
if "until" in df.columns:
    df["deadline_latency"] = df.apply(
        lambda r: r["finish_time"] if r["completed"] == 1 else r["until"], axis=1
    )
else:
    df["deadline_latency"] = df["finish_time"]

summary_rows = []
group_cols = ["protocol", "mobile", "n_participants", "loss"]

for keys, g in df.groupby(group_cols):
    protocol, mobile, n_participants, loss = keys
    row = {
        "protocol": protocol,
        "mobile": mobile,
        "n_participants": n_participants,
        "loss": loss,
        "completion_rate": g["completed"].mean(),
        "coordinator_decision_rate": g["coordinator_decided"].mean() if "coordinator_decided" in g else float("nan"),
        "partial_delivery_rate": g["partial_delivery"].mean() if "partial_delivery" in g else float("nan"),
        "atomicity_violation_rate": g["atomicity_violation"].mean() if "atomicity_violation" in g else float("nan"),
        "avg_deadline_latency": g["deadline_latency"].mean(),
        "avg_msg_sent": g["msg_sent"].mean(),
    }
    summary_rows.append(row)

summary = pd.DataFrame(summary_rows).sort_values(["mobile", "protocol", "n_participants", "loss"])
summary.to_csv(ROOT / "data" / "summary_by_n_loss.csv", index=False)

PROTOCOL_STYLE = {
    "ONE_SHOT": ("C0", "-"),
    "2PC":      ("C1", "--"),
    "2PC_RETRY": ("C2", "-."),
}
N_MARKER = {3: "o", 5: "s", 8: "^"}

def plot_metric(metric, ylabel, filename):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    for ax, mobile in zip(axes, [False, True]):
        sub = summary[summary["mobile"] == mobile]
        for protocol in sorted(sub["protocol"].unique()):
            color, ls = PROTOCOL_STYLE.get(protocol, ("C3", ":"))
            for n in sorted(sub["n_participants"].unique()):
                g = sub[(sub["protocol"] == protocol) & (sub["n_participants"] == n)].sort_values("loss")
                if g.empty:
                    continue
                marker = N_MARKER.get(n, "D")
                label = f"{protocol} n={n}"
                ax.plot(g["loss"], g[metric], color=color, linestyle=ls,
                        marker=marker, label=label)
        ax.set_title("Mobile" if mobile else "Static")
        ax.set_xlabel("Packet loss probability")
        ax.grid(True, alpha=0.3)
    axes[0].set_ylabel(ylabel)
    handles, labels = axes[0].get_legend_handles_labels()
    if handles:
        axes[1].legend(handles, labels, fontsize=7, loc="best")
    fig.tight_layout()
    fig.savefig(fig_dir / filename, dpi=200)
    plt.close(fig)

plot_metric("completion_rate",          "Completion rate",                          "completion_vs_loss.png")
plot_metric("coordinator_decision_rate","Coordinator decision rate",                "coord_decision_vs_loss.png")
plot_metric("partial_delivery_rate",    "Incomplete decision delivery rate",        "partial_delivery_vs_loss.png")
plot_metric("atomicity_violation_rate", "Atomicity violation rate (contradictory)", "atomicity_vs_loss.png")
plot_metric("avg_deadline_latency",     "Deadline-penalized latency",               "latency_vs_loss.png")
plot_metric("avg_msg_sent",             "Average messages sent",                    "messages_vs_loss.png")
