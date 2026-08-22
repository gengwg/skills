---
name: kubespray-node-rejoin
description: Use when re-adding or repairing a node (control-plane or worker) in a kubespray-managed cluster with ansible-playbook, when a play returns UNREACHABLE or failed=1, or when a rejoined node needs verification (taints, cordon, etcd membership)
---

# Kubespray Node Rejoin

## Overview

Rejoining a node with kubespray is a scoped ansible run plus verification. The failure modes are mostly around *where you run it from*, *how you watch it*, and *what you check after* — not the playbook itself.

## Run it right

1. **Scope with `--limit`** — never run cluster-wide for a one-node repair:
   ```sh
   ansible-playbook -i inventory/<cluster>/inventory.ini scale.yml -b --limit=<node>
   ```
   (Control-plane rejoin may need `cluster.yml` with the node in the right groups; `scale.yml` is for adding workers.) Use the repo's pinned environment (venv) — kubespray is version-sensitive to ansible.
2. **Run from a host that can actually reach the nodes.** If your workstation can't SSH to the cluster's network, run the playbook on a host that can (over SSH with a generous timeout), not through hacks on your side.
3. **Watch, don't block.** A rejoin runs 10–40+ minutes. Run it as a background task and poll for the `PLAY RECAP` line rather than sitting on a blocking terminal that a dropped SSH connection kills. `tmux`/`nohup` + tailing the log both work.

## Read the recap correctly

`PLAY RECAP` has two distinct failure classes:

- `failed=N` — a task ran and failed on the node. Read the last failed task; usually node-local (packages, kubelet, certs).
- `unreachable=N` — an SSH/network/bastion problem, not kubespray: either ansible never got in, or (if `ok`/`changed` are nonzero) the connection dropped mid-play, leaving a partial apply. Either way: fix reachability and re-run scoped — kubespray plays are idempotent, so re-running over a partial apply is the normal recovery. No amount of playbook debugging helps.

`failed=0 unreachable=0` on every host = the run succeeded — anything else means re-run after fixing, still scoped with `--limit`.

## Verify after (the run "succeeding" is not the node being back)

```sh
kubectl get node <node>                          # Ready?
kubectl describe node <node> | grep -A5 Taints   # unexpected taints? still cordoned?
kubectl uncordon <node>                          # if it was cordoned for the repair
```

For control-plane nodes, also confirm etcd membership from a healthy member:

```sh
kubectl -n kube-system exec etcd-<healthy-node> -- etcdctl \
  --cacert=/etc/ssl/etcd/ssl/ca.pem \
  --cert=/etc/ssl/etcd/ssl/admin-<healthy-node>.pem \
  --key=/etc/ssl/etcd/ssl/admin-<healthy-node>-key.pem \
  member list
```

All members present, none `unstarted`, one leader.

## Watch for cert drift

A node that was out of the cluster during a cert rotation can rejoin with **stale etcd client certificates** — things mostly work until the API server or etcd starts rejecting it. If the rejoined node logs TLS errors against etcd, compare cert serials/dates under `/etc/ssl/etcd/ssl/` with a healthy node's and re-run the kubespray cert steps for that node.

## Common mistakes

- Running without `--limit` — a repair run becomes a cluster-wide change.
- Debugging the playbook when the recap says `unreachable` — that's networking.
- Blocking a fragile SSH session on a 30-minute play instead of backgrounding it.
- Stopping at `failed=0` without checking Ready/taints/cordon — kubespray doesn't uncordon for you.
- Forgetting etcd membership check on control-plane rejoins.
