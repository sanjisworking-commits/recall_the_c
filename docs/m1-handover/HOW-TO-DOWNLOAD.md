# Getting a non-empty copy of the review ZIPs

`plus.zip`, `pro.zip`, and `max.zip` in this folder are real Zip archives. A browser Download of those binary files, and Cursor's binary attachment download, saves them as **0 KB**. The bytes below are the archives that are actually stored.

| File | Bytes | SHA-256 |
|---|---:|---|
| `plus.zip` | 2830914 | `ec751fb1080407d5631c8f8d47fb649fe7cbae6f25dd443f1ef9c7d2279c6574` |
| `pro.zip` | 2971871 | `92395f1142eae0418cdb305575f6d8adf39b7c1e1fa6a7840f7b45a942fc3ffc` |
| `max.zip` | 2884070 | `4a9dbed5f71b9e6fb7e35506214f575ad3873565199a093948bc760cec24258a` |
| `free-pre-grant.zip` | 7299235 | `ff090fbfdded1bb1de538e745697d51d8098440b0e3d97f24c1ac65e9d0358c4` |

## Plain-text parts

`b64/` holds the same bytes as wrapped Base64 (76-character lines). Those files are text, so a normal download is not empty. From a checkout of this branch:

```bash
python3 docs/m1-handover/restore.py "$HOME/Downloads"
```

That writes the four ZIPs into `~/Downloads` and refuses to write a file whose SHA-256 does not match the table above. `CLAUDE-REVIEW.md` and `manifest.json` are already text; download those directly.

If a saved `.zip` is 0 KB, delete it and use the restored file. Do not review the empty download.
