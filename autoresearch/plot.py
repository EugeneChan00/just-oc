"""
autoresearch.plot

Generate score-over-rounds plots for all agents from git history.
Usage: python -m autoresearch.plot [--out autoresearch/plots]
"""

import argparse
import re
import subprocess
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker


def parse_git_log() -> dict[str, list[dict]]:
    """Parse git log for autoresearch commits, return {agent: [{round, score, accepted}]}."""
    result = subprocess.run(
        ["git", "log", "--oneline", "--grep=autoresearch:"],
        capture_output=True, text=True, timeout=10,
    )
    pattern = re.compile(
        r"autoresearch: (\S+) round (\d+) \((accepted|rejected), score=([\d.]+)\)"
    )
    agents: dict[str, list[dict]] = defaultdict(list)
    for line in result.stdout.strip().splitlines():
        m = pattern.search(line)
        if m:
            agent, rnd, status, score = m.groups()
            agents[agent].append({
                "round": int(rnd),
                "score": float(score),
                "accepted": status == "accepted",
            })
    # Reverse so rounds are in chronological order (git log is newest-first)
    for agent in agents:
        agents[agent] = sorted(agents[agent], key=lambda x: x["round"])
    return dict(agents)


def plot_agent(agent: str, rounds: list[dict], out_dir: Path) -> Path:
    """Plot one agent's score trajectory."""
    fig, ax = plt.subplots(figsize=(10, 4))

    xs = [r["round"] for r in rounds]
    ys = [r["score"] for r in rounds]
    accepted = [r["accepted"] for r in rounds]

    # Track best score line
    best_scores = []
    best = 0.0
    for r in rounds:
        if r["accepted"]:
            best = max(best, r["score"])
        best_scores.append(best)

    # Plot all scores
    ax.plot(xs, ys, color="#888888", linewidth=1, alpha=0.5, zorder=1)

    # Scatter: green=accepted, red=rejected
    for x, y, acc in zip(xs, ys, accepted):
        color = "#2ecc71" if acc else "#e74c3c"
        marker = "o" if acc else "x"
        ax.scatter(x, y, color=color, marker=marker, s=60, zorder=3)

    # Best score envelope
    ax.step(xs, best_scores, color="#3498db", linewidth=2, where="post",
            label="Best score", zorder=2)

    ax.set_xlabel("Round", fontsize=11)
    ax.set_ylabel("Score", fontsize=11)
    ax.set_title(f"{agent}", fontsize=13, fontweight="bold")
    ax.set_ylim(-0.05, 1.05)
    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right", fontsize=9)

    # Legend for markers
    ax.scatter([], [], color="#2ecc71", marker="o", label="Accepted")
    ax.scatter([], [], color="#e74c3c", marker="x", label="Rejected")
    ax.legend(loc="lower right", fontsize=9)

    fig.tight_layout()
    path = out_dir / f"{agent}.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_all_agents(agents: dict[str, list[dict]], out_dir: Path) -> Path:
    """Combined plot with all agents on one chart."""
    fig, ax = plt.subplots(figsize=(14, 6))

    colors = plt.cm.tab20.colors  # type: ignore[attr-defined]

    for i, (agent, rounds) in enumerate(sorted(agents.items())):
        xs = [r["round"] for r in rounds]
        # Best score envelope only
        best = 0.0
        best_scores = []
        for r in rounds:
            if r["accepted"]:
                best = max(best, r["score"])
            best_scores.append(best)

        color = colors[i % len(colors)]
        ax.plot(xs, best_scores, linewidth=2, color=color, label=agent, marker=".", markersize=4)

    ax.set_xlabel("Round", fontsize=11)
    ax.set_ylabel("Best Score", fontsize=11)
    ax.set_title("AutoResearch: All Agents Score Progression", fontsize=14, fontweight="bold")
    ax.set_ylim(-0.05, 1.05)
    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right", fontsize=7, ncol=2)
    fig.tight_layout()

    path = out_dir / "all_agents.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def main():
    parser = argparse.ArgumentParser(description="Plot autoresearch score trajectories")
    parser.add_argument("--out", type=str, default="autoresearch/plots",
                        help="Output directory for plots (default: autoresearch/plots)")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    agents = parse_git_log()
    if not agents:
        print("No autoresearch commits found in git log.")
        return

    print(f"Found {len(agents)} agents with {sum(len(v) for v in agents.values())} total rounds")

    for agent, rounds in sorted(agents.items()):
        path = plot_agent(agent, rounds, out_dir)
        best = max((r["score"] for r in rounds if r["accepted"]), default=0)
        print(f"  {agent}: {len(rounds)} rounds, best={best:.3f} → {path}")

    combined = plot_all_agents(agents, out_dir)
    print(f"\n  Combined → {combined}")


if __name__ == "__main__":
    main()
