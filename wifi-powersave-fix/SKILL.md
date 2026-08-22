---
name: wifi-powersave-fix
description: Disable NetworkManager WiFi power-saving for lower latency and steadier throughput on a Linux dev machine. Use when 'wifi is slow', 'wifi is laggy', 'high wifi latency', 'wifi latency spikes', 'disable wifi power saving', or when onboarding a new Linux developer machine that mostly stays plugged in.
---

# Skill: wifi-powersave-fix

## Purpose

Linux wireless cards default to a power-saving mode that parks the
radio between packets. On a mostly-stationary, mostly-plugged-in dev
machine this shows up as laggy WiFi — higher latency, latency spikes,
and inconsistent throughput. This skill turns power-saving **off** via
a persistent NetworkManager drop-in, trading a little idle power draw
for a steadier link.

It is the first, cheapest thing to try when someone reports "my WiFi
is slow/laggy" on a NetworkManager-managed Linux box.

## When to invoke

- WiFi feels laggy, latency is high/spiky, or throughput is inconsistent.
- Onboarding a new Linux developer machine.
- You want the fix to persist across reboots (NetworkManager re-applies
  it on every connection).

## Prerequisites

- Linux with **NetworkManager** managing the connection (check:
  `systemctl is-active NetworkManager`).
- `sudo` privileges.
- `iw` installed (`iw --version`; on Debian/Ubuntu: `sudo apt install iw`).

## Procedure

### 1. Detect the wireless interface

Do **not** assume the interface name — it varies by machine (`wlp2s0`,
`wlan0`, `wlp3s0`, …).

```sh
IFACE=$(iw dev | awk '/Interface/{print $2; exit}')
[ -n "$IFACE" ] || { echo "No wireless interface found (is 'iw' installed / does this box have WiFi?)"; }
echo "$IFACE"
```

If the machine has **more than one** wireless device (a second NIC or a
USB dongle), `awk` takes the first one — run `iw dev` and set `IFACE`
manually to the device you mean to tune.

### 2. Check the current power-save state

```sh
iw dev "$IFACE" get power_save
```

If it already says `Power save: off` and it's persistent (step 3
config present), there's nothing to do. Otherwise continue.

### 3. Write the NetworkManager drop-in

```sh
sudo tee /etc/NetworkManager/conf.d/wifi-powersave.conf > /dev/null <<'EOF'
[connection]
# Disable WiFi power saving for better throughput/latency
# 2 = disable powersave, 3 = enable powersave
wifi.powersave = 2
EOF
```

Use a `conf.d/` drop-in — do **not** hand-edit
`/etc/NetworkManager/NetworkManager.conf` directly.

### 4. Restart NetworkManager

```sh
sudo systemctl restart NetworkManager
```

### 5. Verify

```sh
iw dev "$IFACE" get power_save   # -> Power save: off
```

Expected output: `Power save: off`. The setting now persists across
reboots and reconnections.

> If it still reads `Power save: on` immediately after the restart, the
> radio may not have re-associated yet — wait a few seconds and re-run
> the check before concluding the fix failed.

## Quick reference

```sh
# Power-save state
iw dev <iface> get power_save

# Current link (band / freq / signal)
iw dev <iface> link

# Band/channel setting on the active connection profile
nmcli -f 802-11-wireless.band,802-11-wireless.channel connection show <profile>

# Regulatory domain (confirms all legal channels/power are available)
iw reg get
```

## If it's still slow — bigger levers

Roughly ordered most- to least-impactful. The power-save tweak above is
the cheapest, but these move the needle more:

1. **Wired connection 🥇** — a USB-C/USB-A gigabit (or 2.5G) adapter
   beats any WiFi tuning: lower latency, no contention, no interference.
   Best choice for a stationary machine.
2. **USB WiFi 6/6E dongle** — if wired isn't feasible and the internal
   card is weak. Pick a chipset with good *mainline* Linux support
   (e.g. MediaTek MT7921/MT7922, Intel AX210); avoid out-of-tree DKMS
   drivers.
3. **Upgrade the kernel** — a newer kernel ships newer WiFi drivers
   (`iwlwifi`, `mt76`) and firmware that fix throughput/roaming/power-save
   bugs. On Ubuntu, the **HWE stack** pulls a newer kernel on an LTS
   release. Low-risk and reversible (GRUB keeps old kernels). Check with
   `uname -r`.
4. **Upgrade the OS / switch backend** — a full distro upgrade brings a
   newer kernel plus newer `wpa_supplicant`, NetworkManager, and
   linux-firmware together. Consider switching the backend from
   `wpa_supplicant` to **`iwd`** for more reliable roaming/stability.
5. **Router-side & environment** — use a clean/less-congested 5 GHz
   channel, enable WPA3, use 80/160 MHz channel width, keep router
   firmware current, set the correct regulatory domain (`iw reg get`),
   and reduce distance/obstructions (placement beats any software knob).

## Optional: hard-lock to 5 GHz

By default the profile does not pin a band (`802-11-wireless.band`
unset, `channel 0` = auto), so it can fall back to 2.4 GHz. To force
5 GHz on a specific profile:

```sh
nmcli connection modify <profile> 802-11-wireless.band a   # a = 5GHz, bg = 2.4GHz
nmcli connection up <profile>
```

Only do this if you're sure of consistent 5 GHz coverage — a hard lock
means no 2.4 GHz fallback when the signal drops.

## Common mistakes

- **Assuming the interface is `wlp2s0`.** Always detect it (step 1) —
  names differ per machine.
- **Editing `NetworkManager.conf` directly** instead of a `conf.d/`
  drop-in. Use the drop-in so upgrades don't clobber it.
- **Forgetting `systemctl restart NetworkManager`.** The config won't
  take effect until NetworkManager reloads.
- **`powersave` value confusion:** `2` = force-disable, `3` = enable.
  Setting `3` does the opposite of what you want here.
