# Published DFS slates: one salary file per site per week, so visitors do not upload one

1. On the site's website (a computer), open the week's main contest: DraftKings → its draft page → **Export to CSV**
   (`DKSalaries.csv`); FanDuel → its lineup page → **Download players list**.
2. Do not edit the file. Rename it `<season>-w<week>-<dk|fd>.csv` — two-digit week: `2026-w06-dk.csv`, `2026-w06-fd.csv`.
   Another contest of the same week gets a label: `2026-w06-dk-showdown.csv` (lower-case letters and digits, up to 20).
3. Put it in this folder, commit, push: the next deploy publishes it (the site reads the folder once when it starts).
4. Check `/api/dfs/slates`: the file is listed with how many players matched ours, or under `unreadable` with the reason.
   Only this week's and next week's files are offered; older ones stay listed as not offered (delete them when you like).
5. Never commit anything but the site's own export (no edited salaries, no other site's data). docs/DFS.md has the rules.
