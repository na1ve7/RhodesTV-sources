# Deployment

## 1. Create + push this repo

Repository: **na1ve7/RhodesTV-sources** (GitHub, public)

```bash
cd RhodesTV-sources
git init -b main
git add -A && git commit -m "init"
git remote add origin git@github.com:na1ve7/RhodesTV-sources.git
git push -u origin main
```

## 2. Enable auto refresh (GitHub Actions)

1. Repo -> Settings -> Actions -> General -> Workflow permissions = **Read and write**
2. (Optional) Settings -> Secrets and variables -> Actions, add for the Gitee mirror:
   - `GITEE_TOKEN`: Gitee personal access token (scope: projects)
   - `GITEE_REPO`: `<gitee_user>/RhodesTV-sources`
   Without these the Gitee step prints "Secrets not set, skip Gitee push" and exits 0.
3. Actions -> "Refresh IPTV Sources" -> **Run workflow** (first run creates `dist/`).

## 3. Trigger from phone

Open `https://github.com/na1ve7/RhodesTV-sources/actions/workflows/refresh.yml` -> **Run workflow**.
Wait 3-5 minutes; the TV picks up the new list on next start (or within 6 hours).

## 4. Update timing on TV

- On app start: uses cache first, refreshes in background
- WorkManager: every 6 hours
- Settings page: "Update now" button

## 5. Troubleshooting

| Symptom | Fix |
|---|---|
| All lines failed | Check subscription URL returns content in a browser |
| One channel black screen | App auto-switches to the next line of that channel |
| "No network" on TV | DNS poisoning: router DNS -> 223.5.5.5 / 119.29.29.29 |
| No EPG | Check tvg-id matches the XMLTV channel id |
