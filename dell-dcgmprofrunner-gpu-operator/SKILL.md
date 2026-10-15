---
name: dell-dcgmprofrunner-gpu-operator
description: Use when Dell support asks for dcgmprofrunner.sh / dcgmproftester thermal output for a hot or throttling GPU on a Kubernetes node where the NVIDIA GPU Operator owns the driver, when the provider proposes reinstalling the server to run it, or when reading its thermal_results CSV to decide cooling fault vs silicon
---

# Dell dcgmprofrunner on GPU Operator–Managed Nodes

## Overview

Dell GPU Engineering gates a thermal case on `dcgmprofrunner.sh` (15 min of `dcgmproftester` tensor load on all GPUs, 1 s telemetry, BMC readings). Its README assumes a host install: nvidia-smi, DCGM, ipmitool, bc, dmidecode, racadm or iDRAC Redfish credentials. On a GPU Operator node none of that is on the host, so the provider's reflex is "reinstall the server and we run it". Decline: a reinstall wipes node identity and labels, forces a cluster rejoin, and the node often comes back different (host driver pre-installed, missing RAID). The script runs unmodified inside the node's **`nvidia-dcgm` pod**, which has everything DCGM-side and can `apt-get` the rest.

## Preconditions

- Node cordoned, no workloads (the load is on all 8 GPUs). On a customer-managed cluster the cordon is theirs; confirm it, do not add your own.
- Human sign-off on `kubectl exec` into a production pod.
- Dell's zip from their MFT portal (per-case credentials; never commit or paste them).
- Dell may require: root, uninterrupted, `ipmitool sensor get "Inlet Temp"` working. The pod route meets all three.

## Run it

```bash
# 1. The nvidia-dcgm-* pod, NOT nvidia-dcgm-exporter-* (no dcgmproftester there)
kubectl -n gpu-operator get pods --field-selector spec.nodeName=<node> | grep nvidia-dcgm-

# 2. Tools the script expects. The pod is privileged, so /dev/ipmi0 is visible
#    and inlet temp + service tag resolve. A CUDA apt-repo cert warning is harmless.
kubectl -n gpu-operator exec <pod> -c nvidia-dcgm-ctr -- bash -c \
  'DEBIAN_FRONTEND=noninteractive apt-get update -qq; apt-get install -y -qq ipmitool bc dmidecode;
   ipmitool sensor get "Inlet Temp" | grep Reading; dmidecode -s system-serial-number'

# 3. Settings: altitude_ft=<datacenter elevation, feet> in dcgmprofsettings.ini, IDRAC_* left unset.
#    hostname shim, or the CSV is named after the pod.
mkdir -p dellprof/shim && printf '#!/bin/sh\necho <node>\n' > dellprof/shim/hostname

# 4. Baseline map; keep it. UUID/PCI is how you track a card after a swap.
kubectl -n gpu-operator exec <pod> -c nvidia-dcgm-ctr -- nvidia-smi \
  --query-gpu=index,uuid,pci.bus_id,serial,temperature.gpu,power.draw --format=csv

# 5. Copy a CLEAN dir (script, ini, README, shim/). Never reuse a previous node's
#    tarball: it carries that run's CSV and that node's hostname shim.
kubectl -n gpu-operator cp dellprof <pod>:/tmp/dellprof -c nvidia-dcgm-ctr

# 6. Detached, stdin from /dev/null so the iDRAC prompts fall through and the run
#    outlives the exec session. An interactive exec dies with your terminal.
kubectl -n gpu-operator exec <pod> -c nvidia-dcgm-ctr -- bash -c \
  'cd /tmp/dellprof && chmod +x dcgmprofrunner.sh shim/hostname &&
   PATH=/tmp/dellprof/shim:$PATH setsid nohup ./dcgmprofrunner.sh </dev/null >run.log 2>&1 &
   sleep 8; tail -5 run.log'

# 7. ~15 min load + a few min of sed post-processing. Done when run.log ends "Finished!".
#    Build the zip from out/dellprof.
kubectl -n gpu-operator cp <pod>:/tmp/dellprof out/dellprof -c nvidia-dcgm-ctr
```

Expected noise: `curl: command not found`, `Unable to determine SupportAssist EULA status`. The exec in step 6 may not return until the script ends; check from another exec. A pod restart (driver upgrade, operator reconcile) kills the run; hold those off for 20 min. No apt egress from the pod: skip step 2, the BMC columns stay empty, and NOTES.txt says so.

Agent harnesses with a command classifier tend to block writes into a production pod (`kubectl cp` in, stdin tar) while allowing reads, the in-pod `apt-get`, and `kubectl cp` out. Have the human run steps 5 and 6 with an absolute local path.

## Bundle for Dell

Zip name per Dell's README: `<SERVICETAG>-dcgmproftest-<YYYY-MM-DD>.zip`. Include everything the script wrote plus the step 4 baseline and a `NOTES.txt`: script version unmodified, target 1004 (TensorEngineActive) 900 s all GPUs, start time UTC, driver version, run as root in the GPU Operator DCGM container; inlet temp and air pressure are real in-band readings; no racadm/curl/iDRAC credentials, so **fans were not forced to 100%, there is no TSR/SupportAssist, and `bmc.fan.pwm=100` is a placeholder**. The TSR comes from whoever holds the iDRAC.

## Read the result

`dcgmproftester` prints PASSED for a card that throttled the whole run. Read the 1 s CSV instead with the bundled script: `sh <this-skill-dir>/summarize.sh thermal_results.*.csv dcgmproftester.log` gives per-GPU max core/HBM, min T.limit, load power and SM clock, slowdown seconds, inlet, TFLOPS. Load averages use power >= 150 W (`utilization.gpu` reads ~70% under tensor load); TFLOPS come from the log because Dell's script passes `--no-dcgm-validation`, which leaves `tensor_active_N.results` empty.

- One card at its T.limit within a minute, held at a fraction of its peers' power, clocks and TFLOPS, with `0x20` (SW thermal slowdown) most of the run, inlet normal, no Xid/ECC/row-remap: cooling path at that position. Ask for a cold-plate/TIM/flow check, not an RMA.
- All GPUs hot: inlet or chassis airflow.
- Hot card at higher power for the same work: silicon.
- `0x80` (HW power brake) on **all** GPUs at the same second: chassis-level, usually a PSU losing AC or redundancy, not a GPU. Split stats before/after it or healthy peers look throttled; ask for the iDRAC SEL and PSU logs around that timestamp.
- Also scan `clocks_event_reasons.active` minute by minute; a whole-run average hides a mid-run change. Bits: `0x04` SW power cap (normal at 690 W), `0x20` SW thermal (per card), `0x40` HW slowdown and `0x80` HW power brake (board/BMC signals).

## After the intervention

Verify by **GPU UUID**, never index or slot. A "GPU relocation" moves the bad card to another slot; index-based and iDRAC slot-based checks then both say healthy while the heat has followed the card. Compare idle `nvidia-smi --query-gpu=uuid,pci.bus_id,temperature.gpu` against the step 4 baseline.

## Cleanup

`rm -rf /tmp/dellprof` in the pod. `dcgmproftester` leaves 8 defunct children under nv-hostengine (PID 1, does not reap); they hold nothing and go away on the next pod restart. Not a reason to delete the pod.

## Common mistakes

- Running the script interactively in `kubectl exec -it`: it hangs on the iDRAC prompts, then dies with the session.
- Patching the script (bc to awk, stripping BMC calls) instead of installing the tools in the pod. Dell wants it unmodified.
- Using the dcgm-exporter pod or a fresh debug pod: no `dcgmproftester`, no live hostengine.
- Shipping a CSV named after the pod, or a zip without the limits spelled out, so Dell asks for a rerun.
- Trusting PASSED, or gating load samples on `utilization.gpu`.
