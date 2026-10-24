---
name: ubuntu-auto-upgrades-off
description: Use when Ubuntu hosts (GPU nodes especially) must not auto-upgrade packages, when you believe unattended upgrades are disabled but packages keep changing, when an apt lock is held by a days-old apt or unattended-upgrade process, or when apt reports a half-configured kernel whose DKMS build fails.
---

# Make Ubuntu automatic upgrades actually stop

## Overview

On GPU hosts, unattended upgrades are a real risk: a `systemd`/`udev` upgrade fires `udevadm trigger`, which the NVIDIA driver and fabric-manager stack does not tolerate, and a new kernel lands without a matching DKMS driver build. Many "disable unattended upgrades" switches only stop part of the mechanism. Verify the state per host; don't trust the setting.

## How the upgrades actually run

```
apt-daily.timer          -> apt-daily.service          -> apt.systemd.daily update   (refresh lists)
apt-daily-upgrade.timer  -> apt-daily-upgrade.service  -> apt.systemd.daily install  -> unattended-upgrade
```

`unattended-upgrades.service` is only the shutdown hook (it waits for an in-flight upgrade at shutdown). Stopping or disabling it does nothing to the timers. Kubespray's `ubuntu_stop_unattended_upgrades: true`, for example, only stops that service.

## Is a host exposed?

A host auto-upgrades only when all three hold:

1. `apt-daily-upgrade.timer` is active (`systemctl is-active apt-daily-upgrade.timer`)
2. `APT::Periodic::Unattended-Upgrade` is `1` (`apt-config dump | grep Unattended-Upgrade`)
3. the `unattended-upgrades` package is installed (`test -x /usr/bin/unattended-upgrade`)

Read-only sweep over an inventory:

```sh
ansible all -i <inventory> -f 10 -o -m ansible.builtin.shell -a \
 'echo "STATE $(systemctl is-enabled apt-daily-upgrade.timer | tail -1) $(systemctl is-active apt-daily-upgrade.timer) $(test -x /usr/bin/unattended-upgrade && echo uu || echo nouu) p=$(apt-config dump | sed -n "s/^APT::Periodic::Unattended-Upgrade \"\(.*\)\";/\1/p")"'
# exposed: "STATE ... active uu p=1"
```

`systemctl is-enabled` on a removed unit prints several lines; keep `| tail -1` or the line breaks parsing.

## Switch it off

Mask the timers, mask the hook, and set the periodic values to 0. A 99- file sorts after `20auto-upgrades`, so its values win.

```yaml
- name: Stop automatic apt upgrades
  hosts: all
  gather_facts: false
  become: true
  tasks:
    - name: Mask the apt timers
      ansible.builtin.systemd:
        name: "{{ item }}"
        state: stopped
        enabled: false
        masked: true
      loop: [apt-daily.timer, apt-daily-upgrade.timer]
    - name: Mask unattended-upgrades.service
      # mask only: stop/disable on a unit that no longer exists fails the play
      ansible.builtin.systemd:
        name: unattended-upgrades.service
        masked: true
    - name: Turn off apt periodic jobs
      ansible.builtin.copy:
        dest: /etc/apt/apt.conf.d/99-disable-periodic-upgrades
        content: |
          APT::Periodic::Update-Package-Lists "0";
          APT::Periodic::Download-Upgradeable-Packages "0";
          APT::Periodic::Unattended-Upgrade "0";
        mode: "0644"
```

Run it with `--check` on a few hosts in each state first (timer active, package removed, already masked). Add it to the new-host build steps, or the next reimage brings the timer back.

Deliberate patches still work with the timers masked: `apt-get update && apt-get install --only-upgrade <pkg>`, or the ansible `apt` module with `only_upgrade: true update_cache: true`.

## Hosts you can't SSH to, but Kubernetes runs on

A short-lived privileged DaemonSet works. Use the host's own namespaces: `chroot /host` does not reach the host's systemd (`systemctl` fails quietly and changes nothing), while `nsenter` into PID 1 does.

```yaml
spec:
  template:
    spec:
      hostPID: true
      tolerations: [{operator: Exists}]
      containers:
        - name: mask
          image: busybox:<pinned>
          securityContext: {privileged: true}
          command: ["/bin/sh", "-c", "nsenter -t 1 -m -u -i -n -p -- /bin/sh -c 'systemctl mask --now apt-daily.timer apt-daily-upgrade.timer; echo RESULT $(hostname) $(systemctl is-enabled apt-daily-upgrade.timer)'; sleep 86400"]
```

Count the `RESULT` lines against the node count, then delete the DaemonSet straight away.

## What earlier upgrades leave behind

- **Wedged apt processes.** An `apt-get` or `python3` (unattended-upgrade) process holding `/var/lib/apt/lists/lock` for days or months blocks every later install. Find it with `fuser /var/lib/apt/lists/lock` plus `ps -o comm=,etime= -p <pid>`, and stop that exact PID. Never kill an upgrade that is running normally: stopping dpkg mid-install leaves packages half-configured.
- **A half-configured kernel.** Unattended upgrades install a new `linux-image` whose postinst runs DKMS; when the host NVIDIA driver can't build for it, configure fails, and every later `apt-get install` retries it and reports `dpkg returned an error code (1)`, even though the package you asked for installed fine. Check what boots next before worrying: `GRUB_DEFAULT` pinned to the running kernel and no `initrd.img` for the new one means a reboot still boots the old kernel.

## Common mistakes

| Mistake | Fix |
|---|---|
| Trusting a "stop unattended upgrades" setting | Sweep the three conditions per host |
| Masking only `unattended-upgrades.service` | Mask `apt-daily-upgrade.timer` (and `apt-daily.timer`) |
| `systemctl stop/disable` in ansible on a removed unit | Mask only for that unit |
| `chroot /host systemctl ...` in a DaemonSet | `hostPID: true` and `nsenter -t 1 -m -u -i -n -p` |
| Reading `dpkg returned an error` as "my package failed" | Check `dpkg-query -W <pkg>`; the error is often a pending kernel |
| Killing an apt process to clear a lock without checking its age | Only kill a wedged one, by exact PID |
