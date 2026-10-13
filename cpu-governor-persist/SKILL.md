---
name: cpu-governor-persist
description: Use when a Linux host must boot with a specific CPU frequency scaling governor (performance, schedutil, powersave) and a manual `echo performance > /sys/.../scaling_governor` reverts after reboot, or when writing or reviewing a systemd unit or Ansible playbook that sets scaling_governor at boot.
---

# Skill: cpu-governor-persist

## Purpose

`scaling_governor` is runtime kernel state. Writing it by hand works until
the next reboot or re-image, and "survives a reboot" is usually the actual
request. The durable form is a systemd oneshot unit that is the only writer:
applying now means restarting that unit, so the boot path is the path you
just exercised.

(On kernels 5.9+ the `cpufreq.default_governor=` kernel parameter is the
other durable form; the same competing-manager caveat below applies.)

Acceptance is the reboot, not the run. `ansible-lint`, `--check` and
`systemd-analyze verify` all pass over a unit that cannot work, because none
of them start it.

## The unit

```ini
[Unit]
Description=Set CPU frequency governor to performance
After=sysinit.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'set -e; for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do echo performance > "$g"; done'

[Install]
WantedBy=multi-user.target
```

Two things in it are load-bearing:

- `set -e`. A rejected or partial write becomes a failed unit instead of a
  success that configured some of the CPUs.
- No `ConditionPathExists`. A failed condition skips the unit and reports the
  start job successful, which is the worst response to cpufreq being absent.
  Refuse at install time instead.

`$g` needs no escaping: systemd expands `${VAR}` anywhere and `$VAR` only as
a word of its own, so a variable inside the quoted `sh -c` script reaches the
shell intact (`$$g` also works). Checked on systemd 259 with a throwaway user
unit; do the same rather than reasoning from the docs.

## Playbook

`set-cpu-governor.yml` in this directory installs the unit and fails closed
on everything the unit cannot check for itself. Canary one host, then drop
`--limit`:

```bash
ansible-playbook -i <inventory> set-cpu-governor.yml \
  -e cpu_governor_hosts=<group> --limit '<group>[0]'
```

`cpu_governor_hosts` defaults to a group that does not exist, so a forgotten
`-e` matches no hosts instead of touching every one. `-e cpu_governor=<name>`
picks the governor; the same flag reverts.

Before writing anything it checks, per host, and fails closed naming the
offender:

- no other governor manager is active or enabled: `power-profiles-daemon`,
  `tuned`, `tlp`, `ondemand`, `cpufrequtils`. Any of them reasserts the governor after
  the unit runs. The unit then reports `enabled`, `active`, `Result=success`,
  and every policy is back on the old value. Nothing at apply time can see
  this; only a reboot does. Mask the manager or configure it to set the
  governor you want, then rerun. Installing the unit by hand skips this
  check, so run that task's shell loop yourself first;
- every cpufreq policy offers the requested governor (a rejected write to
  `scaling_governor` is silently ignored, so an unsupported value leaves the
  host looking configured);
- policy count equals `getconf _NPROCESSORS_CONF` and `online` equals
  `present`. Not `nproc`: it is affinity-scoped, so offlining a CPU drops it
  and its policy together and the comparison goes blind.

## Test on a laptop first

Any machine with cpufreq proves the unit end to end in a minute. An
`intel_pstate` laptop offers only `performance powersave`; that is enough.

```bash
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors
sudo ansible-playbook -i localhost, -c local -e cpu_governor_hosts=all set-cpu-governor.yml
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor | sort | uniq -c
systemctl is-enabled cpu-governor.service
```

Run the whole playbook under `sudo`, in a real terminal, so `become` is a
no-op. Three failures otherwise: an agent's `!` shell has non-blocking stdio
and ansible refuses with "Ansible requires blocking IO"; `--ask-become-pass`
times out when PAM prints a plain `Password:` instead of the prompt ansible
expects; a cached `sudo -v` does not help because become runs `sudo -n`.

Revert: same command with `-e cpu_governor=powersave`.

Expect the manager guard to refuse on most laptops: desktop Ubuntu ships
`power-profiles-daemon`, and many laptops run `tlp`. The right fix there is
to tell that manager what you want (`powerprofilesctl set performance`, or
`CPU_SCALING_GOVERNOR_ON_AC=performance` in `/etc/tlp.d/`), not to mask it
for a test. The unit was observed losing to `power-profiles-daemon` after a
reboot with `Result=success` in the journal.

## Verify on the canary

Record the boot time, apply, reboot, then:

```bash
uptime -s
systemctl is-enabled cpu-governor.service
journalctl -b -u cpu-governor.service --no-pager
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor | sort -u
```

Boot time moved and the last command prints one line, the governor you asked
for. Both together are the proof: the governor alone looks identical if the
host never rebooted. Recheck a couple of minutes after boot: a competing
manager may write the governor well after the unit has finished. Only after
the canary passes a reboot do the fleet run.

The governor takes effect immediately and restarts nothing, so applying needs
no drain. `performance` pins every core to its top P-state, a permanent power
increase the datacenter carries; tell whoever pays for it before a fleet run.

## Common mistakes

- `ConditionPathExists` on the sysfs path. Skipped unit, green start job.
- Reading `scaling_available_governors` from cpu0 only.
- Comparing policy count to `nproc`.
- Installing the unit beside an active `power-profiles-daemon`, `tuned` or
  `tlp`. Green run, green unit, setting gone after boot.
- Calling a green playbook run "persistent". Only a reboot shows that.
- Assuming a built-in cpufreq driver. With a modular driver the unit can run
  before policies exist and fail at boot, visible only in the journal; add
  the module to `/etc/modules-load.d/` or order the unit after it.
