---
name: nvidia-bug-report-gpu-operator
description: Use when generating an nvidia-bug-report, running nvidia-smi, or checking ECC/Xid errors on a Kubernetes GPU node where the driver is managed by the NVIDIA GPU Operator — nothing NVIDIA is on the host PATH and installing drivers via apt makes it worse
---

# nvidia-bug-report on GPU Operator–Managed Nodes

## Overview

On GPU Operator–managed nodes the NVIDIA driver runs inside a container and is bind-mounted onto the host at `/run/nvidia/driver`. Consequences:

- `nvidia-smi`, `nvidia-bug-report.sh`, etc. are **not on the host `$PATH`**
- `dpkg -l | grep nvidia` shows nothing on the host — that's normal, not a broken install
- Do **not** `apt install nvidia-utils-*` — it installs a second, conflicting driver stack on top of the Operator-managed one
- The kernel modules (`nvidia`, `nvidia_uvm`, `nvidia_modeset`) ARE loaded into the host kernel and show up in `lsmod`

## Precheck: do not run nvidia-smi on a latched NVLink node

On B200/B300 nodes with long uptime (observed around 50 to 66 days), the kernel log can fill with:

```
knvlinkUpdatePostRxDetectLinkMask_IMPL: Failed to update Rx Detect Link mask
```

On such a node any `nvidia-smi` call, even `--query-gpu`, goes into uninterruptible D state, cannot be killed, and takes dcgm-exporter down with it. The bug report collector calls `nvidia-smi`, so it hangs the same way. Check first:

```bash
sudo dmesg | grep -c 'Rx Detect Link mask'; uptime
```

If it matches, run neither. Read the VBIOS from `/proc/driver/nvidia/gpus/*/information` instead. The remedy is a reboot now and a GPU tray firmware update from the vendor, not a hardware RMA.

## Locate the tools

```bash
find / -iname "nvidia-bug-report*" 2>/dev/null
# typically: /run/nvidia/driver/usr/bin/nvidia-bug-report.sh
```

## Generate the report

Running the script directly often isn't enough — its internal `nvidia-smi` call needs both the binary dir and the shared-library dir:

```bash
cd /tmp   # report is written to cwd as nvidia-bug-report.log.gz

# confirm the exact lib dir first and USE WHAT IT PRINTS below —
# Ubuntu-based driver images use usr/lib/x86_64-linux-gnu, RHEL/UBI-based use usr/lib64
sudo find /run/nvidia/driver -iname "libnvidia-ml.so*"

sudo env PATH="/run/nvidia/driver/usr/bin:$PATH" \
     LD_LIBRARY_PATH="/run/nvidia/driver/usr/lib/x86_64-linux-gnu" \
     /run/nvidia/driver/usr/bin/nvidia-bug-report.sh
```

Use `sudo env`, not `sudo VAR=...` — default sudoers scrubs `LD_*` assignments (with or without an error), and the report then ships with its SMI sections silently skipped.

On a GPU actively throwing ECC/Xid errors the collector itself can wedge on `nvidia-smi`/`nvidia-debugdump` — if it hangs, re-run with `--safe-mode`.

Check the **"Summary of Skipped Sections"** printed at the end. `NVIDIA SMI` and `NVIDIA GPU Details` must NOT appear there — if they show "not found" or a `libnvidia-ml.so` failure, the PATH/LD_LIBRARY_PATH point at the wrong dirs; re-run the `find` above.

Remaining skips (`glxinfo`, `xrandr`, `vulkaninfo`, `acpidump`, `mst`, `nvlsm-bug-report.sh`) are expected and harmless on headless compute nodes with no display or InfiniBand subnet manager.

**Alternative — chroot** resolves all driver libs the way the driver container would:

```bash
sudo chroot /run/nvidia/driver nvidia-bug-report.sh
```

Caveat: inside the chroot you lose the host's own `dmesg`/`lspci`/etc., so some non-NVIDIA sections come out less complete. Prefer the PATH/LD_LIBRARY_PATH form for reports you'll send to a vendor.

**If `/run/nvidia/driver` is empty or missing**, the driver daemonset isn't healthy on this node — check `kubectl -n gpu-operator get pods -o wide | grep <node>` before anything else. A working alternative that skips host-env problems entirely: `kubectl exec` into the node's `nvidia-driver-daemonset` container, run `nvidia-bug-report.sh` there, and `kubectl cp` the file out.

## Quick ECC / GPU check without a full report

```bash
sudo chroot /run/nvidia/driver nvidia-smi -q -d ECC

# map GPU index <-> UUID <-> PCI bus id (needed to confirm "GPU 3" claims from alerts)
sudo chroot /run/nvidia/driver nvidia-smi \
  --query-gpu=index,uuid,pci.bus_id,ecc.errors.uncorrected.aggregate.total \
  --format=csv
```

Join on **UUID or `pci.bus_id`**, not index — monitoring stacks (DCGM exporter carries all three as labels) and vendors disagree on GPU numbering, and an RMA for the wrong physical card starts here. (With MIG enabled, a monitoring "GPU N" may not be a physical GPU at all.)

Two things `aggregate.total` won't tell you: it's a lifetime counter, so nonzero doesn't confirm a *current* alert — compare the volatile counters in `-q -d ECC` — and on A100/H100-class parts the actual RMA criterion is row remapping: check `nvidia-smi -q -d ROW_REMAPPER` for pending/failed remaps before drafting the vendor request.

## Get the report off the node and inspect it

```bash
scp -J <user>@<jumphost> <user>@<node-ip>:/tmp/nvidia-bug-report.log.gz .

zcat nvidia-bug-report.log.gz | less   # /ECC or /Xid jumps to the section
gunzip -k nvidia-bug-report.log.gz     # extract a copy, keep the .gz
```

Skim it before uploading anywhere — confirm it actually captured the GPU sections, and know what it says before the vendor does.

**Do not attach the `.gz` in Slack Connect.** It is rejected ("Files of this type can't be shared in conversations using Slack Connect"). What has worked is the uncompressed log renamed to `.txt`, or the vendor's ticket portal. A `.zip` is untested there; use it only once you have seen it accepted. The uncompressed log can run to hundreds of MB, so delete it after uploading:

```bash
gunzip -c nvidia-bug-report.log.gz > <node>-nvidia-bug-report-<date>.txt
```

## Common mistakes

- `apt install nvidia-utils` to "fix" the missing nvidia-smi — now two driver stacks fight.
- Running `nvidia-bug-report.sh` bare and shipping a report whose SMI sections silently failed — always read the skipped-sections summary.
- Trusting a monitoring system's GPU index without confirming against `pci.bus_id`.
- Concluding the driver is broken because `dpkg` shows no NVIDIA packages.
- Attaching the raw `.log.gz` to a Slack Connect channel. Send a `.txt` or use the vendor portal.
- Running `nvidia-smi` on a node logging the Rx Detect error. It hangs for good.
