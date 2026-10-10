---
name: gpu-operator-driver-uncordon
description: Use when a GPU node cordoned for a hardware fault (Xid 79, GPU fallen off the bus, ECC, NVLink) is schedulable again after a reboot or driver pod restart and nobody uncordoned it, when a faulted GPU node must stay out of service through a planned reboot, or when auditing an NVIDIA GPU Operator fleet for faulted nodes silently returned to service.
---

# GPU Operator driver pod uncordons faulted nodes

## Overview

With the containerized driver, the `k8s-driver-manager` init container of the
`nvidia-driver-daemonset` pod uncordons the node every time it runs, whether
or not it placed the cordon. A node cordoned for a bad GPU comes back
schedulable a minute or two after any reboot and takes work on the faulted
GPU until it fails again.

No released version fixes this, so an upgrade is not the remedy. Status as of
2026-10; re-check before quoting it:

- [k8s-driver-manager#212](https://github.com/NVIDIA/k8s-driver-manager/issues/212): the bug, open.
- [#258](https://github.com/NVIDIA/k8s-driver-manager/pull/258), merged 2026-10-06: only records the node's initial state in an annotation. Uncordon is still unconditional.
- [#282](https://github.com/NVIDIA/k8s-driver-manager/pull/282): the proposed fix, open. As written it makes the driver wait on any node someone else cordoned, so a faulted node would reboot with no driver and no `nvidia-smi` or DCGM for triage.

## Exposure

- **Exposed:** ClusterPolicy `spec.driver.enabled: true` and `ENABLE_GPU_POD_EVICTION` or `ENABLE_AUTO_DRAIN` true in the driver-manager env. Eviction defaults to `"true"`. On the reboot path the uncordon runs before any driver is loaded (`cmd/driver-manager/main.go`, the `isGPUPodEvictionEnabled() || isAutoDrainEnabled()` branch).
- **Not exposed:** a preinstalled host driver (`driver.enabled: false`), since no driver pod runs.
- `driver.upgradePolicy.autoUpgrade: false` does not help. This is the init container, not the upgrade controller.

## Prove it

```bash
kubectl --context <ctx> get node <node> -o jsonpath='{.status.nodeInfo.bootID}{"\n"}'
kubectl --context <ctx> -n gpu-operator get pod -l app=nvidia-driver-daemonset \
  --field-selector spec.nodeName=<node> -o wide
kubectl --context <ctx> -n gpu-operator logs <driver-pod> -c k8s-driver-manager | grep -i cordon
# "Uncordoning node <node>" shortly after pod start = this bug
```

Container logs only cover the current run. For older events use the API audit
log: a `patch` on `nodes/<node>` by
`system:serviceaccount:gpu-operator:nvidia-driver` (namespace may differ),
or whatever "uncordoned-by" record your health controller keeps:

```bash
jq -c 'select(.verb=="patch" and .objectRef.resource=="nodes"
  and (.user.username | test("nvidia-driver")))
  | [.requestReceivedTimestamp, .objectRef.name, .user.username]' audit.log
```

With no audit log and no controller record, the driver pod start time
matching the uncordon within a minute or two of boot is the best evidence.

## Keep a faulted node out through a reboot

Apply the change before the reboot and leave the existing cordon in place.

| Option | Cost |
|---|---|
| Hold the reboot until the hardware is fixed | None. Prefer it. |
| Label `nvidia.com/gpu.deploy.driver=false` | No driver pod, so nothing uncordons. Removes the driver from the whole node: healthy GPUs, `nvidia-smi` and DCGM go too. Set it back to `true` after the repair or the node returns with 0 GPUs. |
| Custom `NoSchedule` taint | Driver-manager leaves taints alone, but pods with a blanket `operator: Exists` toleration (common on GPU jobs and DaemonSets) still land. Check tolerations first; remove after repair. |
| Re-cordon after the driver pod finishes | A race: pods schedule in the gap. Not a fix. |

## Fleet sweep

List nodes whose last uncordon came from the driver service account, then
sort each hit into a legitimate return or a lifted cordon:

- Legitimate: GPU UUIDs changed (`nvidia-smi -L`, so the card was replaced), vendor ticket closed, or someone recorded a decision to return it.
- Lifted by the bug: a cordon reason or fault ticket still open, the same GPU UUID, and no record of a repair.

Run the sweep against a node known to be affected first. An empty result
without that positive control proves nothing. A last-actor record shows only
the most recent uncordon, so an older driver uncordon that a person later
repeated will not show.

## Common mistakes

- Blaming the upgrade controller and setting `autoUpgrade: false`.
- Expecting a GPU Operator upgrade to fix it.
- Re-cordoning and rebooting again without one of the options above.
- Leaving `nvidia.com/gpu.deploy.driver=false` on a repaired node.
- Calling a node a victim only because its uncordon actor is the driver. The driver uncordon is also the normal last step of a deliberate return.
