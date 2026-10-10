---
name: infiniband-port-alerting-pitfalls
description: Use when reading or alerting on InfiniBand/RoCE port state on GPU nodes (node_infiniband_state_id, node_infiniband_physical_state_id, ibstat, mlx5 devices), when HGX B200/B300 nodes show four extra mlx5 ports at 100G reading INIT, DOWN or ACTIVE, when an "IB rail down" rule fires on many nodes at once and resolves as NoData, or before reporting down IB ports to a datacenter provider.
---

# InfiniBand port alerting pitfalls

## Overview

Port-state metrics look like a simple "is the rail up" check. On GPU nodes,
some ports are not rails at all, some are switched off on purpose, and some
vanish from the metrics. Each case below either pages on nothing or hides a
real dead rail.

## 1. HGX B200/B300 bridge ports are not a fabric

The baseboard carries one ConnectX-7 mezzanine, exposed as four mlx5
functions (CX-Bridge), wired only to the NVSwitch complex. No cable, no
switch. NVLSM, the NVLink subnet manager shipped in the driver, runs on the
node and manages NVLink through them. Fabric Manager uses them, so never
unbind them.

- They read INIT or DOWN whenever the driver or NVLSM is not up, and ACTIVE with LIDs when it is. LIDs here do not prove an IB fabric or a provider-run SM.
- Their device names move between server layouts (seen as `mlx5_4-7`, `5-8`, `6-9`, `7-10`, `8-11`). A name list is correct for one layout only.
- Never file them with a provider as down links, and keep them out of RDMA device-plugin pools so no pod is handed one.

Identify by hardware, not by name:

```bash
for d in /sys/class/infiniband/*; do
  pci=$(readlink -f "$d/device")
  printf '%s %s rate=%s board=%s width=x%s\n' "$(basename "$d")" "$(basename "$pci")" \
    "$(cat "$d/ports/1/rate")" "$(cat "$d/board_id")" "$(cat "$pci/max_link_width")"
done
```

Bridges are functions `.0-.3` of one PCI device, 100G, `LnkCap` width x2.
Rails each sit on their own bus at x16 and 400G or more. The width is the
link capability (`LnkCap` in `lspci -vv`), so it holds with no driver
loaded. `board_id` also differs between rail and bridge parts: record your
fleet's pair once.

## 2. Never dismiss a down port by name or rate alone

The reverse error costs more. A dead 400G rail whose name matches a bridge
name on another layout reads as "the usual non-fabric port" and can go
unnoticed for weeks. A broken rail has also been seen reporting 10 Gb/s, so a
rate-based rail filter drops exactly the broken one. Check the PCI tell, then
compare the same device on healthy peers of the same layout.

## 3. Physical state 3 is configuration, not a fault

| `state_id` | `physical_state_id` | Meaning |
|---|---|---|
| 4 Active | 5 LinkUp | Healthy |
| 2 Init | 5 LinkUp | Link up, no SM sweep yet: post-reboot race or SM stall |
| any | 2 Polling | No link partner: cable, optic or far end |
| any | 4 PortConfigurationTraining | Partner present, training never completes |
| any | 3 Disabled | Switched off on purpose. Exclude from down rules |

A rail in Polling or PortConfigurationTraining while the same rail on peers
is Active is a provider ticket. Count non-Active ports only after excluding
Disabled ones. A port that keeps
cycling into Disabled by itself is different: firmware or thermal shutdown.

## 4. Exclusions must hold per sample, inside the lookback window

This rule pages when unused Disabled ports are unbound and stop reporting:

```promql
min_over_time(node_infiniband_state_id[30m]) < 4
unless on (instance, device) node_infiniband_physical_state_id == 3
```

The window still holds 30 minutes of old down samples, but the `unless` sees
only the current sample, which is now absent. Every unbound port fires, then
resolves as NoData once the window empties. Put the exclusion inside the
subquery so each sample is judged with its own physical state:

```promql
count_over_time(
  (
    (max by (instance, device) (node_infiniband_state_id) < 4)
    unless on (instance, device)
    (max by (instance, device) (node_infiniband_physical_state_id) == 3)
  )[30m:1m]
) >= 2
and on (instance) (max by (instance) (up{job="node-exporter"}) == 1)
```

A port that stays Disabled never fires, even after it disappears. One that is
re-enabled but stays down fires after two samples. An instant rule with
`for:` also avoids the bug but resets on every bounce. Backtest any change
over the window that contained the false page.

## Common mistakes

- Treating four 100G ports at INIT on every node as a fleet-wide fabric fault.
- Hard-coding bridge device names in a rule and copying it to another layout.
- Reading LIDs or a live SM as evidence of a provider-run InfiniBand fabric.
- Counting raw non-Active ports to size a problem before excluding Disabled ones.
- Unbinding unused ports without checking which rules key on their series.
