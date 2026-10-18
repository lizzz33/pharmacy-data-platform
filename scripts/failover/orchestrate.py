#!/usr/bin/env python3
"""Explicit host-side orchestration for HW1 experiments E1-E7.

Disruptive actions only occur in the named e2-e3/e4/e5/e6 commands. Every such
command performs the standard readiness check before the first disruption and
again after restoring the cluster.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "reports" / "failover"
POSTGRES_MEMBERS = ("postgres1", "postgres2", "postgres3")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Evidence:
    def __init__(self, name):
        self.directory = REPORT_ROOT / name
        self.directory.mkdir(parents=True, exist_ok=True)
        self.commands = self.directory / "commands.txt"

    def record(self, command):
        rendered = subprocess.list2cmdline([str(item) for item in command])
        with self.commands.open("a", encoding="utf-8") as output:
            output.write(f"[{utc_now()}] {rendered}\n")

    def run(self, command, *, output=None, check=True, timeout=None):
        self.record(command)
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        if output:
            (self.directory / output).write_text(completed.stdout, encoding="utf-8")
        else:
            print(completed.stdout, end="")
        if check and completed.returncode:
            raise RuntimeError(f"command failed ({completed.returncode}): {subprocess.list2cmdline(command)}")
        return completed

    def start(self, command, output):
        self.record(command)
        stream = (self.directory / output).open("w", encoding="utf-8")
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            text=True,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
        process.evidence_stream = stream
        return process

    def finish(self, process, timeout=180):
        returncode = process.wait(timeout=timeout)
        process.evidence_stream.close()
        if returncode:
            raise RuntimeError(f"background load failed with exit status {returncode}")

    def write_json(self, name, value):
        (self.directory / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def docker(*args):
    return ["docker", "compose", *args]


def ready(evidence):
    evidence.run(["./scripts/wait_ready.sh", "--timeout", "240"], output=f"wait-ready-{int(time.time())}.log")


def topology():
    last_error = None
    for port in (8008, 8009, 8010):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/cluster", timeout=3) as response:
                return json.load(response)
        except Exception as error:
            last_error = error
    raise RuntimeError(f"all Patroni REST endpoints failed: {type(last_error).__name__}")


def member(role, *, exclude=None):
    matches = [item["name"] for item in topology().get("members", []) if item.get("role") == role]
    if exclude:
        matches = [name for name in matches if name != exclude]
    if not matches:
        raise RuntimeError(f"no Patroni member with role={role!r}")
    return matches[0]


def wait_until(description, predicate, timeout=90, interval=1):
    started = time.monotonic()
    last_error = None
    while time.monotonic() - started < timeout:
        try:
            value = predicate()
            if value:
                return value, round(time.monotonic() - started, 3)
        except Exception as error:
            last_error = error
        time.sleep(interval)
    suffix = f" ({type(last_error).__name__})" if last_error else ""
    raise TimeoutError(f"timeout waiting for {description}{suffix}")


def load_command(label, duration):
    base = f"/reports/failover/{label}"
    return docker(
        "run", "--rm", "-T", "--no-deps", "tools", "python", "scripts/failover/write_load.py",
        "--duration", str(duration), "--run-id", f"{label}-{int(time.time())}",
        "--events", f"{base}/write-events.jsonl", "--summary", f"{base}/write-summary.json",
    )


def collect_topology(evidence, name):
    value = topology()
    evidence.write_json(name, value)
    return value


def collect_patroni_logs(evidence, since):
    evidence.run(
        docker("logs", "--since", since, "postgres1", "postgres2", "postgres3"),
        output="patroni.log",
        check=False,
    )


def experiment_e1():
    evidence = Evidence("e1-baseline")
    ready(evidence)
    collect_topology(evidence, "topology-before.json")
    host = {
        "captured_at": utc_now(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
    }
    evidence.write_json("host.json", host)
    evidence.run(["docker", "version"], output="docker-version.txt")
    evidence.run(["docker", "compose", "version"], output="compose-version.txt")
    command = load_command("e1-baseline", 60)
    evidence.run(command, output="write-load.stdout", timeout=90)
    collect_topology(evidence, "topology-after.json")


def experiment_e2_e3(label="e2-e3-failover"):
    evidence = Evidence(label)
    ready(evidence)
    since = utc_now()
    before = collect_topology(evidence, "topology-before.json")
    old_leader = next(item["name"] for item in before["members"] if item["role"] == "leader")
    process = evidence.start(load_command(label, 70), "write-load.stdout")
    metadata = {"started_at": since, "old_leader": old_leader}
    try:
        time.sleep(10)
        metadata["leader_stopped_at"] = utc_now()
        # `kill` is unsuitable here because restart: unless-stopped immediately
        # revives the container. A zero-grace explicit stop keeps it down until E3.
        evidence.run(docker("stop", "-t", "0", old_leader), output="leader-stop.txt")
        new_leader, promotion_s = wait_until(
            "a different Patroni leader",
            lambda: (candidate if (candidate := member("leader")) != old_leader else None),
            timeout=60,
        )
        metadata.update({"new_leader": new_leader, "promotion_observed_s": promotion_s})
        metadata["old_node_started_at"] = utc_now()
        restart_started = time.monotonic()
        evidence.run(docker("start", old_leader), output="old-node-start.txt")

        def old_member_streaming():
            old = next((item for item in topology()["members"] if item["name"] == old_leader), None)
            return old and old.get("role") in {"replica", "sync_standby"} and old.get("state") == "streaming"

        _, rejoin_s = wait_until("old leader to return as streaming replica", old_member_streaming, timeout=120)
        metadata["rejoin_s"] = round(time.monotonic() - restart_started, 3)
        metadata["rejoin_observed_s"] = rejoin_s
        metadata["old_node_role_after_return"] = next(
            item["role"] for item in topology()["members"] if item["name"] == old_leader
        )
    finally:
        state = subprocess.run(docker("ps", "-q", old_leader), cwd=ROOT, text=True, capture_output=True)
        if not state.stdout.strip():
            evidence.run(docker("start", old_leader), output="emergency-old-node-start.txt", check=False)
        evidence.finish(process, timeout=120)
    ready(evidence)
    collect_topology(evidence, "topology-after.json")
    collect_patroni_logs(evidence, since)
    evidence.write_json("experiment.json", metadata)


def experiment_e4():
    evidence = Evidence("e4-switchover")
    ready(evidence)
    since = utc_now()
    before = collect_topology(evidence, "topology-before.json")
    old_leader = next(item["name"] for item in before["members"] if item["role"] == "leader")
    candidate = next(item["name"] for item in before["members"] if item["role"] == "replica")
    process = evidence.start(load_command("e4-switchover", 45), "write-load.stdout")
    time.sleep(10)
    switched_at = utc_now()
    evidence.run(
        docker(
            "exec", "-T", old_leader, "patronictl", "-c", "/etc/patroni/patroni.yml",
            "switchover", "pharmacy-hw1", "--leader", old_leader, "--candidate", candidate, "--force",
        ),
        output="switchover.txt",
    )
    new_leader, observed_s = wait_until("switchover candidate to become leader", lambda: member("leader") == candidate)
    evidence.finish(process, timeout=90)
    ready(evidence)
    collect_topology(evidence, "topology-after.json")
    collect_patroni_logs(evidence, since)
    evidence.write_json(
        "experiment.json",
        {
            "started_at": since,
            "switchover_requested_at": switched_at,
            "old_leader": old_leader,
            "candidate": candidate,
            "new_leader": candidate if new_leader else None,
            "new_leader_observed_s": observed_s,
        },
    )


def patroni_config(evidence, synchronous):
    contact = member("leader")
    value = "true" if synchronous else "false"
    return evidence.run(
        docker(
            "exec", "-T", contact, "patronictl", "-c", "/etc/patroni/patroni.yml",
            "edit-config", "pharmacy-hw1", "--set", f"synchronous_mode={value}", "--force",
        ),
        output=f"sync-{value}.txt",
    )


def experiment_e5():
    evidence = Evidence("e5-synchronous")
    ready(evidence)
    since = utc_now()
    evidence.run(load_command("e5-async-baseline", 30), output="async-load.stdout", timeout=60)
    patroni_config(evidence, True)
    time.sleep(12)
    evidence.run(
        docker("exec", "-T", member("leader"), "patronictl", "-c", "/etc/patroni/patroni.yml", "show-config", "pharmacy-hw1"),
        output="sync-config.txt",
    )
    evidence.run(load_command("e5-sync-baseline", 30), output="sync-load.stdout", timeout=60)
    old_leader = member("leader")
    process = evidence.start(load_command("e5-sync-failover", 70), "sync-failover-load.stdout")
    metadata = {"started_at": since, "old_leader": old_leader}
    try:
        time.sleep(10)
        evidence.run(docker("stop", "-t", "0", old_leader), output="sync-leader-stop.txt")
        new_leader, promotion_s = wait_until(
            "sync failover leader",
            lambda: (candidate if (candidate := member("leader")) != old_leader else None),
            timeout=60,
        )
        metadata.update({"new_leader": new_leader, "promotion_observed_s": promotion_s})
        evidence.run(docker("start", old_leader), output="sync-old-node-start.txt")
        wait_until(
            "sync old leader to rejoin",
            lambda: any(
                item["name"] == old_leader and item.get("state") == "streaming"
                for item in topology().get("members", [])
            ),
            timeout=120,
        )
    finally:
        state = subprocess.run(docker("ps", "-q", old_leader), cwd=ROOT, text=True, capture_output=True)
        if not state.stdout.strip():
            evidence.run(docker("start", old_leader), output="emergency-old-node-start.txt", check=False)
        evidence.finish(process, timeout=120)
        try:
            patroni_config(evidence, False)
        except Exception as error:
            metadata["async_restore_error"] = str(error)
    time.sleep(12)
    ready(evidence)
    collect_topology(evidence, "topology-after.json")
    collect_patroni_logs(evidence, since)
    evidence.write_json("experiment.json", metadata)


def etcd_health(evidence, output, check=True):
    return evidence.run(
        docker(
            "exec", "-T", "etcd1", "/usr/local/bin/etcdctl",
            "--endpoints=http://etcd1:2379,http://etcd2:2379,http://etcd3:2379",
            "endpoint", "health",
        ),
        output=output,
        check=check,
        timeout=20,
    )


def experiment_e6():
    evidence = Evidence("e6-etcd-quorum")
    ready(evidence)
    since = utc_now()
    collect_topology(evidence, "topology-before.json")
    etcd_health(evidence, "etcd-all-healthy.txt")
    metadata = {"started_at": since}
    stopped = []
    try:
        evidence.run(docker("stop", "etcd3"), output="stop-etcd3.txt")
        stopped.append("etcd3")
        time.sleep(8)
        etcd_health(evidence, "etcd-one-down.txt", check=False)
        evidence.run(load_command("e6-one-etcd-down", 15), output="one-down-write.stdout", timeout=45)
        collect_topology(evidence, "topology-one-etcd-down.json")
        evidence.run(docker("start", "etcd3"), output="start-etcd3.txt")
        stopped.remove("etcd3")
        wait_until("all etcd members healthy", lambda: etcd_health(evidence, "etcd-restored-once.txt", check=False).returncode == 0, timeout=60, interval=3)

        process = evidence.start(load_command("e6-quorum-loss", 65), "quorum-loss-write.stdout")
        time.sleep(5)
        metadata["quorum_removed_at"] = utc_now()
        evidence.run(docker("stop", "etcd2", "etcd3"), output="stop-etcd2-etcd3.txt")
        stopped.extend(["etcd2", "etcd3"])
        time.sleep(35)
        etcd_health(evidence, "etcd-quorum-lost.txt", check=False)
        evidence.run(
            docker(
                "run", "--rm", "-T", "--no-deps", "-e", "PGPASSWORD=checker", "tools", "psql",
                "-h", "pgbouncer-ro", "-p", "6432", "-U", "checker", "-d", "pos_service_db",
                "-XAtqc", "SELECT clock_timestamp(), pg_is_in_recovery(), count(*) FROM contract.v_receipt",
            ),
            output="read-during-quorum-loss.txt",
            check=False,
        )
        metadata["quorum_restored_at"] = utc_now()
        evidence.run(docker("start", "etcd2", "etcd3"), output="start-etcd2-etcd3.txt")
        stopped.clear()
        evidence.finish(process, timeout=120)
    finally:
        if stopped:
            evidence.run(docker("start", *stopped), output="emergency-etcd-start.txt", check=False)
    wait_until("all etcd members healthy after quorum loss", lambda: etcd_health(evidence, "etcd-final.txt", check=False).returncode == 0, timeout=90, interval=3)
    ready(evidence)
    collect_topology(evidence, "topology-after.json")
    collect_patroni_logs(evidence, since)
    evidence.write_json("experiment.json", metadata)


def experiment_e7():
    evidence = Evidence("e7-connection-pressure")
    ready(evidence)
    collect_topology(evidence, "topology-before.json")
    evidence.run(
        docker(
            "run", "--rm", "-T", "--no-deps", "tools", "python",
            "scripts/failover/connection_pressure.py", "--levels", "50,100,150,200,250",
            "--hold", "0.5", "--output", "/reports/failover/e7-connection-pressure/results.json",
        ),
        output="connection-pressure.stdout",
        timeout=180,
    )
    ready(evidence)


EXPERIMENTS = {
    "e1": experiment_e1,
    "e2-e3": experiment_e2_e3,
    "e4": experiment_e4,
    "e5": experiment_e5,
    "e6": experiment_e6,
    "e7": experiment_e7,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment", choices=[*EXPERIMENTS, "all"])
    args = parser.parse_args()
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    selected = list(EXPERIMENTS) if args.experiment == "all" else [args.experiment]
    for name in selected:
        print(f"== {name}: started at {utc_now()} ==", flush=True)
        EXPERIMENTS[name]()
        print(f"== {name}: completed at {utc_now()} ==", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as error:
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
