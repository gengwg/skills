# skills

[![skills.sh](https://skills.sh/b/gengwg/skills)](https://skills.sh/gengwg/skills)

Agent skills. Install with the [skills CLI](https://www.skills.sh/):

```bash
npx skills add gengwg/skills -s <name>       # project install
npx skills add gengwg/skills -s <name> -g    # global install

# example
npx skills add gengwg/skills -s medium-post -g
```

| Skill | Use for |
|---|---|
| [medium-post](medium-post/SKILL.md) | Publishing markdown to Medium via browser automation (no API needed) |
| [wifi-powersave-fix](wifi-powersave-fix/SKILL.md) | Fix laggy WiFi on Linux by disabling NetworkManager power saving |
| [dotfiles-multi-machine-sync](dotfiles-multi-machine-sync/SKILL.md) | Dotfiles repo with an idempotent symlink installer, synced across machines |
| [pygame-headless-test-and-release](pygame-headless-test-and-release/SKILL.md) | Test, screenshot, and release pygame apps without a display |
| [grafana-alert-rule-api](grafana-alert-rule-api/SKILL.md) | Silent-failure traps in Grafana's alert-rule provisioning API |
| [grafana-alert-silences](grafana-alert-silences/SKILL.md) | Time-boxed alert silences that match correctly and don't blind aggregates |
| [mirror-repo-data-to-notion](mirror-repo-data-to-notion/SKILL.md) | Mirror git-managed data into Notion with detectable drift |
| [verify-alert-before-replying](verify-alert-before-replying/SKILL.md) | Re-derive an alert's claim from live data before answering "is this real?" |
| [kubespray-node-rejoin](kubespray-node-rejoin/SKILL.md) | Rejoin a node to a kubespray cluster: scoped runs, recap reading, post-verification |
