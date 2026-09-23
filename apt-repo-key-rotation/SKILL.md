---
name: apt-repo-key-rotation
description: Fix a third-party APT repo that fails `apt update` with NO_PUBKEY or "signatures couldn't be verified" after the vendor rotated its signing key (HashiCorp, Docker, NodeSource, etc.). Use when `apt update` shows 'NO_PUBKEY', 'The following signatures couldn't be verified', 'EXPKEYSIG', or 'repository is not signed' for one repo while the others are fine.
---

# Skill: apt-repo-key-rotation

## Purpose

When a vendor rotates its APT signing key, `apt update` logs an `Err` for
that one repo and quietly keeps using the stale index, so upgrades from it
stop arriving. The fix is to replace the keyring the repo's `signed-by`
points at with the vendor's current key. Don't use `apt-key`, which is gone
from current Debian and Ubuntu releases.

## Steps

### 1. Find the keyring apt actually uses

Don't guess the path. Vendor docs say `/usr/share/keyrings/...`, but older
installs often use `/etc/apt/keyrings/...`, and writing to the wrong one
changes nothing.

```bash
rg -n 'signed-by|Signed-By' /etc/apt/sources.list.d/ | rg -i <vendor>
```

The keyring format is set by its extension: `.gpg` is binary (dearmored),
`.asc` is ASCII-armored.

### 2. Confirm the diagnosis

```bash
gpg --show-keys --with-colons /etc/apt/keyrings/<vendor>.gpg | awk -F: '/^(pub|sub)/{print $1, $5, $7}'
```

If the `NO_PUBKEY` ID from the error is not in that list, the key rotated.
`EXPKEYSIG` means the key you have is still valid but past its expiry date,
and the same fix applies.

### 3. Fetch the new key and verify it before installing

```bash
curl -fsSL https://<vendor-apt-host>/gpg -o vendor.asc
gpg --show-keys --with-colons vendor.asc | awk -F: '/^(pub|sub)/{print $1, $5, $7}'
```

Only continue if the missing key ID appears here. Take the URL from the
vendor's own install docs, served over HTTPS.

### 4. Replace it, keeping a backup

```bash
sudo cp /etc/apt/keyrings/<vendor>.gpg{,.bak}
gpg --dearmor < vendor.asc | sudo tee /etc/apt/keyrings/<vendor>.gpg >/dev/null
sudo chmod 644 /etc/apt/keyrings/<vendor>.gpg
sudo apt update
```

For an `.asc` keyring, copy the armored file as-is instead of dearmoring.
The keyring must be world-readable, because apt verifies signatures as the
unprivileged `_apt` user.

### 5. Verify

`apt update` shows a `Get`/`Hit` line for the repo with no `Err` or `W:`
line under it. Once the repo is confirmed working, delete the `.bak` file.

## Agent notes

`sudo` needs a TTY to prompt for a password. From an agent shell, do steps 1
to 3 and then hand the user the step 4 command to run in their own
terminal. Save the fetched key somewhere that outlives the session, or
include the `curl` step in the handed-off command.

## Common mistakes

- Writing the new key to a different path from the one `signed-by` names.
- Installing whatever key the URL returns without checking that it contains
  the missing key ID.
- Dearmoring into a file named `.asc`, or copying armored text into a `.gpg`
  file.
- Using `apt-key add`, which is deprecated and removed.
- Leaving the keyring mode `600`, which fails with "not readable by user
  '_apt'".
