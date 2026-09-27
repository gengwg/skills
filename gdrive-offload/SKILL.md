---
name: gdrive-offload
description: Upload local files to Google Drive (My Drive or a shared drive) with rclone, verify the upload, then delete the local copies. Use when asked to "upload X to gdrive and rm local", "move my Downloads to Drive", "offload files to the shared drive", or to file uploads into Drive folders.
---

# Skill: gdrive-offload

## Purpose

Move files off the local disk into Google Drive without losing anything. Deleting the local copy happens only after `rclone check` shows the remote matches.

Assumes an rclone remote for Google Drive already exists (here `gdrive:`). If `rclone listremotes` shows none, set one up first with `rclone config` (storage `drive`).

## Target: My Drive vs shared drive

- **My Drive:** `gdrive:<path>`
- **Shared drive:** same remote plus `--drive-team-drive <ID>` on **every** command. A URL like `https://drive.google.com/drive/folders/0AIxxxx` whose ID starts with `0A` is a shared drive root, so that ID is the shared drive's ID. `rclone backend drives gdrive:` lists them all.

A My Drive mount (e.g. `~/gdrive`) never shows shared drive files. If the user says "it's not synced", check which drive they are looking at before assuming a failure.

## Procedure

### 1. Inventory and confirm

List what is there before touching anything:

```sh
ls -Ap <dir>
```

Leave these out of the upload:

- Lock files (`.~lock.*#`, `~$*`). A lock file means the document may be open. Check with `pgrep -x soffice.bin` and ask the user to save and close it before you delete the original.
- Tool and config dirs (`.claude/`, `.git/`, `.cache/`).
- Anything that looks personal rather than work data, when the target is a shared drive. Ask. Common cases:
  - Browser profile backups (`Restore Firefox/`, `*.default-release/`, Chrome `User Data/`). They hold saved passwords, cookies and history, so treat them as credentials and never put them on a shared drive.
  - Messaging app data (`xwechat_files/`, `WeChat Files/`, `Telegram Desktop/`, Signal or WhatsApp exports), which contains private chats and received files.
  - App-managed folders that apps create in `~/Documents` (game saves, `Zoom/` recordings, virtual machine images). Uploading them breaks nothing, but they are rarely what the user means.

Show the user the exact file list and the destination, and get a yes. Deletion is irreversible.

### 2. Upload an exact set

Write the confirmed names to a file list rather than using broad globs:

```sh
mkdir -p tmp
printf '%s\n' "file one.pdf" file2.csv > tmp/files.txt
rclone copy <dir> gdrive:<dest> --files-from tmp/files.txt [--drive-team-drive <ID>]
```

For a single file, `rclone copy <file> gdrive:<dest>` is enough. To create a folder, run `rclone mkdir gdrive:<dest>`.

### 3. Verify before deleting

```sh
rclone check <dir> gdrive:<dest> --files-from tmp/files.txt --one-way [--drive-team-drive <ID>]
```

Proceed only on `0 differences found` with the expected `N matching files`.

Drive listings are eventually consistent. A check run immediately after upload can report missing files that are actually there. Wait a few seconds and rerun; never delete on a failed check, and never "fix" it by re-uploading, which creates duplicate files (Drive allows duplicate names).

### 4. Delete local copies

Delete only the verified list, by name:

```sh
cd <dir> && xargs -d '\n' rm -f -- < tmp/files.txt && rm tmp/files.txt
```

Then `ls -A <dir>` to show what is left.

### 5. Organize on the remote (optional)

```sh
rclone moveto "gdrive:file.docx" "gdrive:Folder Name/file.docx" [--drive-team-drive <ID>]
rclone lsf "gdrive:Folder Name" [--drive-team-drive <ID>]
```

`moveto` is a server-side move; nothing is re-uploaded.

## Traps

- **zsh does not word-split variables.** `TD="--drive-team-drive X"; rclone ... $TD` passes one argument and rclone fails with `unknown flag`. Write the flag inline.
- **`lsf --include` still lists directories.** Use `--files-only` when checking that files left a folder.
- **Filenames with spaces or non-ASCII** (en dashes, parentheses) need quotes on the command line; the `--files-from` list handles them as-is.
- **Native Google Docs** show size `-1` in listings. That is normal and not an upload failure.
