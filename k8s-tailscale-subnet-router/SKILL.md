---
name: k8s-tailscale-subnet-router
description: Use when you need SSH or other access to a Kubernetes cluster's node network but the bastion or jump host is closed or unreachable while kubectl still works, or when a Tailscale subnet route is approved yet clients don't get it (no route, "no matching peer", AllowedIPs without the subnet).
---

# Tailscale subnet router in a Kubernetes cluster

## Overview

When the jump host is gone but the API still answers, run Tailscale as one pod inside the cluster, advertise the node network as a subnet route, and reach every node directly over the tailnet. Five steps, two of which fail silently if skipped: the pod's writable paths, and the access policy for the route.

## 1. Deploy the router

Userspace mode needs no `NET_ADMIN` and works non-root. Two paths must be writable: a non-root process can't `chmod` an emptyDir's mount root (so put state in a subdirectory), and `/var/run/tailscale` must exist on a read-only root filesystem. Without them the pod crash-loops with `store.New failed ... chmod /var/lib/tailscale: operation not permitted` before it ever logs in.

```yaml
apiVersion: v1
kind: Namespace
metadata: {name: tailscale-router}
---
apiVersion: apps/v1
kind: Deployment
metadata: {name: subnet-router, namespace: tailscale-router}
spec:
  replicas: 1
  selector: {matchLabels: {app: subnet-router}}
  template:
    metadata: {labels: {app: subnet-router}}
    spec:
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        runAsGroup: 1000
        seccompProfile: {type: RuntimeDefault}
      containers:
        - name: tailscale
          image: tailscale/tailscale:<pinned-version>
          env:
            - {name: TS_AUTHKEY, valueFrom: {secretKeyRef: {name: ts-auth, key: TS_AUTHKEY}}}
            - {name: TS_HOSTNAME, value: <cluster>-router}
            - {name: TS_ROUTES, value: <node-cidr>}
            - {name: TS_USERSPACE, value: "true"}
            - {name: TS_KUBE_SECRET, value: ""}
            - {name: TS_STATE_DIR, value: /var/lib/tailscale/state}
            - {name: TS_SOCKET, value: /tmp/tailscaled.sock}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: {drop: [ALL]}
          resources:
            requests: {cpu: 50m, memory: 64Mi}
            limits: {memory: 256Mi}
          volumeMounts:
            - {name: state, mountPath: /var/lib/tailscale}
            - {name: tmp, mountPath: /tmp}
            - {name: run, mountPath: /var/run/tailscale}
      volumes:
        - {name: state, emptyDir: {}}
        - {name: tmp, emptyDir: {}}
        - {name: run, emptyDir: {}}
```

The pod waits in `CreateContainerConfigError` until the secret exists. That is expected.

## 2. Auth key, without exposing it

Create the key in the admin console (Settings, Keys). For a one-off job: not reusable, 1-day expiry, ephemeral. The human generates and copies it; an agent never reads or relays it. Load it so it never reaches shell history or the process list (`printf` is a builtin):

```sh
read -rs "K?auth key: "; echo          # zsh; in bash: read -rsp 'auth key: ' K
printf 'TS_AUTHKEY=%s\n' "$K" | kubectl -n tailscale-router \
  create secret generic ts-auth --from-env-file=/dev/stdin
unset K
```

Don't use `--from-env-file=<(read ...)` in zsh: the process substitution runs in the background and the prompt hangs.

A one-time ephemeral key with emptyDir state means **a pod restart ends access**: the login is lost and the key is spent. For a lasting router, use a reusable or tagged key and keep state in a Kubernetes Secret (`TS_KUBE_SECRET` plus the RBAC to write it).

Healthy logs show `machineAuthorized=true` and `Startup complete`.

## 3. Approve the route

Machines, the router, Edit route settings, tick the CIDR, Save. (Or an `autoApprovers` entry in the policy.)

## 4. Grant access to the range

An approved route is sent only to peers the policy lets reach an address inside it. Add a rule that names the CIDR, and check that its source actually includes you: `autogroup:admin` is the **Admin** role only, so Network admins and IT admins are not in it. Your role is on the Users page. A rule with `autogroup:admin` as source can look like it should cover you and silently not.

```json
{"src": ["autogroup:admin", "autogroup:network-admin"], "dst": ["<node-cidr>"], "ip": ["*"]}
```

## 5. Accept routes on the client and connect

Linux clients ignore subnet routes until told otherwise. No sudo needed if you are the Tailscale operator (`OperatorUser` in `tailscale debug prefs`):

```sh
tailscale set --accept-routes
tailscale status --json | jq -r '.Peer[] | select(.HostName=="<cluster>-router") | .AllowedIPs | join(",")'
ip route get <a-node-ip>       # must say: dev tailscale0 table 52
```

An `~/.ssh/config` `ProxyJump` for that range still sends you through the dead bastion. Override it:

```sh
ssh -o ProxyJump=none <user>@<node-ip>
ansible-playbook ... -e "ansible_ssh_common_args='-o StrictHostKeyChecking=accept-new -o ProxyJump=none'"
```

## Debugging a route that never arrives

Work from the router outwards:

1. Router side: `kubectl -n tailscale-router exec deploy/subnet-router -- tailscale --socket=/tmp/tailscaled.sock status --json`. `Self.PrimaryRoutes` should list the CIDR. Empty means the route is not advertised or not approved.
2. Client side: the CIDR missing from the router peer's `AllowedIPs` on every client, while the router has it, is the policy (step 4).
3. Present in `AllowedIPs` but `ip route get` goes out the default interface: `--accept-routes` is off.

## Cleanup

Delete the Deployment (and the namespace), remove the policy rule, and remove the machine in the console. An ephemeral node drops off by itself once offline. Some clusters run an admission policy that blocks namespace deletion; deleting the Deployment is enough to cut access.

## Common mistakes

| Mistake | Fix |
|---|---|
| Running the router as root to dodge the `chmod` crash | Keep it non-root; give state a subdirectory and mount `/var/run/tailscale` |
| Pasting the auth key into chat or a command line | `read -s` plus `printf \| ... --from-env-file=/dev/stdin`, typed by the human |
| Approving the route and stopping there | Also grant the CIDR in the policy, and check your role is in the `src` |
| Treating the router as durable access | One-time ephemeral key + emptyDir state dies with the pod |
| Restarting the pod to "fix" a missing route | That loses the login for good with a one-time key; debug from the router outwards instead |
