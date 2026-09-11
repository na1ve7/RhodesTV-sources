# RhodesTV-sources

Auto-maintained IPTV sources for the **RhodesTV（罗德岛TV）** Android TV app.

- `tools/test_sources.py` -> fetch all sources in `sources.txt`, test concurrently, drop dead/blocked ones -> `dist/playable.m3u`
- `tools/gen_epg.py` -> merge XMLTV sources, keep only channels in use -> `dist/epg.xml(.gz)`
- `.github/workflows/refresh.yml` -> runs every 6 hours, commits fresh results; optional mirror push to Gitee

## URLs to put in the TV app (设置页 or http://<TV-IP>:8765/)

| Item | URL |
|---|---|
| Subscription (jsDelivr CDN, fastest in CN) | `https://cdn.jsdelivr.net/gh/na1ve7/RhodesTV-sources@main/dist/playable.m3u` |
| Subscription (GitHub raw) | `https://raw.githubusercontent.com/na1ve7/RhodesTV-sources/main/dist/playable.m3u` |
| EPG (jsDelivr) | `https://cdn.jsdelivr.net/gh/na1ve7/RhodesTV-sources@main/dist/epg.xml.gz` |
| EPG (GitHub raw) | `https://raw.githubusercontent.com/na1ve7/RhodesTV-sources/main/dist/epg.xml.gz` |
| Gitee mirror (optional) | `https://gitee.com/<gitee_user>/RhodesTV-sources/raw/master/dist/playable.m3u` |

> 若 raw.githubusercontent.com 被污染导致电视“网络无连接”，优先用 jsDelivr 或 Gitee 镜像地址。

See [docs/DEPLOY.md](docs/DEPLOY.md).
