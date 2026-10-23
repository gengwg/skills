---
name: ip-abuse-report-triage
description: Use when a hosting provider forwards an abuse report (X-ARF, SIP/VoIP scan, port scan, brute force, spam) that names one of your public IPs, or asks whether a host is compromised. Decide whether the traffic really came from you before rotating, reimaging or blackholing anything
---

# IP Abuse Report Triage

## Overview

An IP that is under attack collects abuse reports for traffic it never sent: the attacker forges it as the source so third-party servers reply to it (reflection). Prove which path could have emitted the reported traffic before treating it as a compromise. Everything here is read-only.

## Steps

1. **Pin the report.** Timestamp in UTC, protocol, source and destination ports, packet count. A handful of UDP packets is the classic forged-source shape.
2. **Can anything emit from that IP?** On the host that owns it, `ip route show default`. If the default route is a private interface, the host's own outbound traffic leaves through NAT. From any node, `curl -s --max-time 5 https://ifconfig.me` gives the real egress address. If it differs from the reported IP, no workload egress carries the reported IP, and the only traffic leaving from it is replies to inbound connections.
3. **Listeners and sockets.** `sudo ss -tulnp` for what listens on all interfaces, and `sudo ss -tunap | grep :<reported-port>`. A protocol nothing speaks cannot be a reply.
4. **Persistence and access.** Check the clock first (`date; date -u`) so log times are read in the right zone. Then:
   - files changed since the suspected window in `/usr/local/bin`, `/usr/local/sbin`, `/tmp`, `/var/tmp`, `/dev/shm`, `/etc/systemd/system`, `/etc/cron.d`, `/root`, plus root and user crontabs
   - logins near the report time (`last -F`, `journalctl -u ssh` "Accepted" lines)
   - every login's key fingerprint mapped to an owner with `ssh-keygen -lf ~/.ssh/authorized_keys`, and the `authorized_keys` modification time
5. **Correlate with inbound traffic.** Graph the public interface's receive rate (`rate(node_network_receive_bytes_total{device="<public-iface>"}[2m])`) around the report time. A report that lands inside a flood window is reflection.
6. **Answer the provider.** Say what was checked and why the source looks forged, ask for the raw report fields (destination, ports, protocol) to confirm, and push for upstream filtering on the IP: the floods are the real problem, and a node firewall cannot stop a link from filling.

## Common mistakes

| Mistake | Fix |
|---|---|
| Assuming the host's public IP is also its outbound address | Check the default route and the real egress IP; NAT often uses a different address |
| Reading journal timestamps as UTC | Run `date` on the host first |
| Calling logins clean because they are key-based | Map each fingerprint to its owner and check when `authorized_keys` last changed |
| Rotating keys or reimaging before checking | It destroys the evidence and does nothing against reflection |
