---
name: kubespray-node-rejoin
description: Use when re-adding or repairing a node (control-plane or worker) in a kubespray-managed cluster with ansible-playbook, when a play returns UNREACHABLE or failed=1, when scale.yml fails the fact-cache assert or an rsync from /tmp/kubespray_cache, when a node vanished from kubectl get nodes while its host is up, when kubelet crash-loops on a missing kubelet-client-current.pem, or when a rejoined node needs verification (taints, cordon, etcd membership)
---

# Kubespray Node Rejoin

## Overview

Rejoining a node with kubespray is a scoped ansible run plus verification. The failure modes are mostly around *where you run it from*, *how you watch it*, and *what you check after* — not the playbook itself.

## First: does it need kubespray at all?

Check the host before planning a rejoin: `uptime -s`, `systemctl is-active kubelet`, `journalctl -u kubelet -n 50`.

| Symptom | Fix |
|---|---|
| Node gone from `kubectl get nodes`, host up, kubelet `active`, journal loops on `nodes "<n>" not found` | The Node object was deleted. kubelet registers only at startup: `systemctl restart kubelet`. Labels and taints died with the object; rebuild them from a sibling node of the same class. |
| kubelet crash-loops on `unable to read client-cert .../kubelet-client-current.pem` and `stat /etc/kubernetes/bootstrap-kubelet.conf: no such file` | Client cert lost. Re-bootstrap it (below). The Node object and its labels survive. |
| Host reimaged (new hostname or host key, no `/etc/kubernetes`) | Real rejoin: continue with this skill. |

**Re-bootstrap a lost kubelet client cert.** On a control-plane node, `kubeadm token create --ttl 1h`. On the worker, write `/etc/kubernetes/bootstrap-kubelet.conf` (mode 600):

```yaml
apiVersion: v1
kind: Config
clusters:
- name: default
  cluster:
    server: https://<control-plane-ip>:6443   # not 127.0.0.1
    certificate-authority: /etc/kubernetes/ssl/ca.crt
users:
- name: kubelet-bootstrap
  user: {token: <token>}
contexts:
- name: default
  context: {cluster: default, user: kubelet-bootstrap}
current-context: default
```

Then `systemctl restart kubelet`. kubeadm's `node-autoapprove-bootstrap` binding approves the CSR, and the node is Ready in seconds. The server must be a real control-plane IP: kubespray's `127.0.0.1:6443` is the nginx-proxy static pod, which this same kubelet runs, so it can never answer. Delete the token afterwards (`kubeadm token delete <id>`).

## Run it right

1. **Scope with `--limit`** — never run cluster-wide for a one-node repair:
   ```sh
   ansible-playbook -i inventory/<cluster>/inventory.ini scale.yml -b --limit=<node>
   ```
   (Control-plane rejoin may need `cluster.yml` with the node in the right groups; `scale.yml` is for adding workers.) Use the repo's pinned environment (venv) — kubespray is version-sensitive to ansible.
2. **Run from a host that can actually reach the nodes.** If your workstation can't SSH to the cluster's network, run the playbook on a host that can (over SSH with a generous timeout), not through hacks on your side.
3. **Watch, don't block.** A rejoin runs 10–40+ minutes. Run it as a background task and poll for the `PLAY RECAP` line rather than sitting on a blocking terminal that a dropped SSH connection kills. `tmux`/`nohup` + tailing the log both work. A playbook that stops for an interactive confirmation needs a real TTY (tmux), not a flag that skips the prompt.

## Before the run: control node and fact cache

- **`--limit` needs a complete fact cache.** The scoped play reads other hosts' facts (etcd and control-plane addresses) from the cache. Run `playbooks/facts.yml` over the whole inventory first, and check the cache holds one entry per inventory host (kubespray `docs/operations/nodes.md`).
- **Through v2.31, one unreachable host empties the cache.** The bootstrap play is `any_errors_fatal: true`, so it aborts, and `facts.yml` exits 0 with `failed=0` everywhere and zero cache files written. `scale.yml` then fails the fact-cache assert. `-e any_errors_fatal=false` cannot help: it is a reserved play keyword, so ansible warns and discards it. Comment the dead host out of the inventory for the run, or run `facts.yml --limit=<reachable hosts>`. From v2.32 the bootstrap play defaults to not fatal, controlled by `kubespray_any_errors_fatal`. Don't reach for `-e ignore_assert_errors=yes`; it disables every preinstall assert to get past one.
- **`download_run_once: true` breaks a `--limit` run.** The download play runs on `kube_control_plane[0]`, which `--limit` excludes, so the cache is never filled and the copy fails with `rsync ... /tmp/kubespray_cache/...: No such file or directory (code 23)`. If the node can reach the registries, rerun with `-e '{"download_run_once": false}'`. The plain `-e download_run_once=false` passes the string `"false"`, which `validate_inventory` rejects as not a bool.
- **`kubelet_rotate_server_certificates: true` needs the approver already running.** `scale.yml` sets the kubelet to request serving certs but doesn't run `kubernetes-apps`, which deploys `kubelet-csr-approver`. Check `kubectl -n kube-system get deploy | grep csr-approver` first. If it is missing, run the `kubernetes-apps` part of `cluster.yml` before scaling, or the node's serving CSRs stay Pending, and `kubectl logs`/`exec` and metrics scrapes of it fail.
- **Snapshot labels and taints before `kubectl delete node`.** A reimaged node's stale Node object is usually deleted before the rejoin, and its hand-applied labels, taints and cordon go with it. NFD and GPU Operator labels come back on their own; nothing restores the rest:
  ```sh
  kubectl get node <n> -o json | jq '{labels: .metadata.labels, taints: .spec.taints, unschedulable: .spec.unschedulable}' > <n>-before.json
  ```
- **Raise the controller's open-file limit.** The common default `ulimit -n 1024` makes `facts.yml` over ~100+ hosts die with `[Errno 24] Too many open files` and cache nothing. Run `ulimit -n $(ulimit -Hn)` in the same shell first.
- **Keep forks low through a bastion** (`-f 6` to `10`). A high fork count trips the bastion's SSH connection limits and shows up as fake `UNREACHABLE` results.
- **A newly reinstalled node** has a new host key (remove the stale `known_hosts` entry) and holds the dpkg lock for a while after boot. Wait for `fuser /var/lib/dpkg/lock-frontend` to clear, or `system_packages` fails.

## Read the recap correctly

`PLAY RECAP` has two distinct failure classes:

- `failed=N` — a task ran and failed on the node. Read the last failed task; usually node-local (packages, kubelet, certs).
- `unreachable=N` — an SSH/network/bastion problem, not kubespray: either ansible never got in, or (if `ok`/`changed` are nonzero) the connection dropped mid-play, leaving a partial apply. Either way: fix reachability and re-run scoped — kubespray plays are idempotent, so re-running over a partial apply is the normal recovery. No amount of playbook debugging helps.

Two `unreachable` causes that are not real network faults:

- **A node mid-reboot.** A few workers that refuse SSH are often rebooting or being recycled. Re-probe them with `-f 1` a minute later before dropping them.
- **An uncached bastion host key** surfaces as `UNREACHABLE! ... Connection closed by UNKNOWN port 65535`. SSH to the bastion directly once to accept its key, then re-run.

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
- Running `--limit` on a stale or partial fact cache.
- Dropping a host from the inventory on one `UNREACHABLE` without re-probing it.
- Running a full rejoin when restarting kubelet or a token re-bootstrap would do, and losing the node's labels in the process.
- Trusting a `facts.yml` exit 0 on v2.31 or older; count the cache files.
