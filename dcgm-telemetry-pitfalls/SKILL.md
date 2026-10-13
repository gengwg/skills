---
name: dcgm-telemetry-pitfalls
description: Use when reading DCGM / dcgm-exporter GPU metrics in Prometheus or Grafana to decide whether a GPU node is healthy or faulted, especially when a series is missing (DCGM_FI_DEV_XID_ERRORS, DCGM_FI_DEV_NVLINK_*), when DCGM_FI_DEV_FABRIC_MANAGER_STATUS reads healthy, when DCGM_FI_PROF_* comes back with no labels, or when an alert rule keyed on a DCGM field name is blind on some clusters.
---

# Skill: dcgm-telemetry-pitfalls

## Purpose

DCGM metrics look like health checks but several of them are event-created,
latched, aggregated, or renamed between exporter versions. Each case below
reads as a fault or as an all-clear and is neither. The common fix is the
same: before trusting absence or a healthy value, check the series' shape
across the fleet and probe a host with a known fault.

## 1. A missing `DCGM_FI_DEV_XID_ERRORS` series usually means no Xid

dcgm-exporter creates the XID series per GPU the first time that GPU records
an Xid. Clean GPUs emit nothing. So "no XID series" is not a coverage gap.

Check the shape before concluding either way:

```promql
count by (Hostname) (DCGM_FI_DEV_XID_ERRORS{cluster="X"})
```

Uniform count per node (8 on an 8-GPU node) means the exporter emits it
always, and absence is a gap. Ragged and growing over a range means
event-created, and absence means no Xid.

Counter-example that must be run: pick a GPU with a known Xid in that cluster
(kernel log, vendor ticket). If it has no series either, the cluster is
blind, and "no Xid" cannot be claimed from telemetry there. Prove health
another way: uptime with no reboot, ECC counters, scrape continuity, and
workload still resident on that GPU index.

## 2. Fabric manager status 3 latches at init

`DCGM_FI_DEV_FABRIC_MANAGER_STATUS` (field 170) reflects GPU-side fabric
registration when nvidia-fabricmanager initialises: 2 in progress, 3
completed, 0 not supported. It catches "fabric manager never finished" and
nothing after that. A node whose NVLink subnet manager died minutes after
boot still reads 3 on every GPU, same as its healthy peers.

Never accept 3 as proof of health after a repair or reboot. Cross-check
against a healthy peer in the same cluster:

```bash
cat /sys/class/infiniband/*/ports/1/state     # every port ACTIVE on a healthy peer
tail /var/log/nvlsm.log                        # healthy: "SUBNET UP"; bad: "SM is not in MASTER state"
```

## 3. Missing NVLink counters are usually the exporter, not the links

An "NVLink dead" rule built on "GPU emits temperature and power but no
`DCGM_FI_DEV_NVLINK_*`" fires when dcgm-exporter stops publishing those
fields for some GPUs while the rest keep flowing. Seen after scrape write
timeouts and pod-mapper rate limiting on the exporter. Seven of eight GPUs
losing links at once, with one untouched, is the exporter.

Confirm on the box before filing a hardware ticket, from the DCGM pod when
SSH is unavailable:

```bash
kubectl --context <ctx> -n gpu-operator exec <nvidia-dcgm-pod> -- dcgmi nvlink -s
```

All links Up and no NVSwitch faults means the fix is on the exporter, and the
alert is a monitoring gap. A Grafana "resolved" with state reason `Updated`
is a rule edit, not recovery; the alert comes back after its pending period.

## 4. Profiling metrics with every label dropped still average

An aggregation layer (Grafana Adaptive Metrics or similar) can drop every
label from `DCGM_FI_PROF_*` and keep only `count` and `sum`. `avg()` and
`avg_over_time()` then fail or return nothing. The fleet-level number is
still there:

```promql
sum(DCGM_FI_PROF_GR_ENGINE_ACTIVE) / count(DCGM_FI_PROF_GR_ENGINE_ACTIVE)
```

Only the per-cluster or per-node breakdown is gone; that needs an aggregation
exemption, not a different query. On one fleet over a week,
`GR_ENGINE_ACTIVE` tracked `DCGM_FI_DEV_GPU_UTIL / 100` within 0.3%, so the
NVML utilisation figure can stand in at fleet scale; spot-check yours first.

## 5. Field names differ between DCGM 3 and DCGM 4 exporters

Rules written against one name set are blind on clusters running the other.
Before declaring a gap or asking a cluster owner for a field, read the rule
and count both names per cluster.

| DCGM 3 name | DCGM 4 name |
|---|---|
| `DCGM_FI_DEV_CLOCK_THROTTLE_REASONS` | `DCGM_FI_DEV_CLOCKS_EVENT_REASONS` |
| `DCGM_FI_DEV_ENFORCED_POWER_LIMIT` | `DCGM_FI_DEV_POWER_MGMT_LIMIT` |
| `DCGM_FI_DEV_PCIE_TX_THROUGHPUT` / `_RX_` | `DCGM_FI_PROF_PCIE_TX_BYTES` / `_RX_` |
| `DCGM_FI_DEV_NVLINK_BANDWIDTH_L0..L17` | `DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL`, `DCGM_FI_PROF_NVLINK_TX_BYTES` / `_RX_` |

Write rules as `metric_a or metric_b` and verify with
`count by (cluster) (metric)` for both names.

## Common mistakes

- Reporting "no Xid" or "no NVLink data" without the shape check in 1 or the
  on-box check in 3.
- Treating field 170 = 3 as current health rather than init history.
- Filing a datacenter ticket on an absence-based rule alone.
- Giving up on `DCGM_FI_PROF_*` because `avg()` returns nothing.
- Declaring a cluster blind without reading the rule; thermal and power rules
  often already `or` both field names.
