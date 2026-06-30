# CI/CD 閮ㄧ讲涓庡洖婊氳鏄?

鏈枃妗ｈ鏄?`aus-ele` 椤圭洰鐨勬寔缁泦鎴?/ 鎸佺画浜や粯锛圕I/CD锛夋祦姘寸嚎璁捐銆佹墍闇€閰嶇疆銆佺敓浜ф湇鍔″櫒鍓嶇疆鍑嗗锛屼互鍙婇儴缃插悗楠岃瘉涓庡け璐ヨ嚜鍔ㄥ洖婊氭満鍒躲€?

---

## 1. 鏉冨▉ Python 鐗堟湰锛?.11

椤圭洰缁熶竴浠?**Python 3.11** 涓哄敮涓€鏉冨▉鐗堟湰锛屼笁澶勫繀椤讳繚鎸佷竴鑷达細

| 浣嶇疆 | 閰嶇疆 | 璇存槑 |
|------|------|------|
| CI 娴佹按绾?| `.github/workflows/ci.yml` 涓?`PYTHON_VERSION: "3.11"` | `backend` 浣滀笟 `setup-python` 浣跨敤璇ョ増鏈?|
| 鍚庣闀滃儚 | `Dockerfile.backend` 涓?`FROM python:3.11-slim` | 鐢熶骇杩愯鏃堕暅鍍忓熀纭€鐗堟湰 |
| 鏈湴寮€鍙?| 鏈湴铏氭嫙鐜锛坴env锛変娇鐢?Python 3.11 | 涓?CI / 闀滃儚瀵归綈锛岄伩鍏嶃€屾湰鍦拌兘璺戙€丆I 澶辫触銆?|

> 鍗囩骇 Python 鐗堟湰鏃讹紝蹇呴』鍚屾鏇存柊浠ヤ笂涓夊锛屽惁鍒欒涓虹牬鍧忔潈濞佺増鏈竴鑷存€с€?

---

## 2. CI/CD 娴佹按绾挎€昏

娴佹按绾跨敱 **6 涓綔涓氾紙Job锛?* 缁勬垚锛屽垎涓?CI 璐ㄩ噺闂ㄤ笌 CD 浜や粯涓ら樁娈碉紝閫氳繃 `needs:` 寤虹珛渚濊禆銆侀€氳繃 `if:` 鎺у埗 CD 浠呭湪 `main` 鍒嗘敮 push 鏃惰Е鍙戙€?

```
backend 鈹€鈹?
         鈹溾攢鈻?build-push 鈹€鈻?deploy 鈹€鈻?verify
frontend 鈹€鈹?                 鈹?         鈹?
                             鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹粹攢鈹€鈻?rollback锛堝け璐ユ椂锛?
```

### 2.1 鍚勪綔涓氳亴璐ｄ笌瑙﹀彂鏉′欢

| 浣滀笟 | 鑱岃矗 | 瑙﹀彂鏉′欢 |
|------|------|----------|
| **backend** | Python 3.11 鐜涓嬫墽琛?mypy 绫诲瀷妫€鏌ャ€佸崟鍏冩祴璇曘€侀泦鎴愭祴璇?| push锛坢ain/develop锛変笌 PR锛坢ain/develop锛夊潎杩愯 |
| **frontend** | ESLint 妫€鏌ャ€佸墠绔崟鍏冩祴璇曘€乣npm run build` 鏋勫缓 | push锛坢ain/develop锛変笌 PR锛坢ain/develop锛夊潎杩愯 |
| **build-push** | 鏋勫缓 backend/web 闀滃儚骞舵帹閫佽嚦 GHCR锛屽悓鏃舵墦 `latest` 涓庡畬鏁?40 浣?commit SHA 鏍囩 | `needs: [backend, frontend]` 涓斾粎 `main` 鍒嗘敮 push |
| **deploy** | 缁?SSH 杩炴帴鐢熶骇鏈嶅姟鍣紝鎷夊彇璇?SHA 闀滃儚骞剁敤 `docker-compose.prod.yml` 閲嶅惎鏈嶅姟 | `needs: [build-push]`锛岀户鎵?main-push 鏉′欢 |
| **verify** | 閮ㄧ讲鍚庡仴搴锋鏌ワ紙Health_Check锛? 鍐掔儫娴嬭瘯锛圫moke_Test锛夛紝閫氳繃鍚庤褰?Last_Stable_Tag | `needs: [deploy]` |
| **rollback** | 澶辫触鏃跺洖婊氬埌涓婁竴绋冲畾鐗堟湰锛圠ast_Stable_Tag锛?| `needs: [deploy, verify]` 涓?`if: failure() && needs.deploy.outputs.deploy_attempted == 'true'` |

### 2.2 鍏抽敭闂ㄦ帶璇存槑

- **CD 浠呭湪 main push 瑙﹀彂**锛歅R 涓?develop 鍒嗘敮鍙窇 CI 璐ㄩ噺闂紝涓嶈Е鍙戞瀯寤烘帹閫佷笌閮ㄧ讲銆?
- **鍥炴粴绮剧‘闂ㄦ帶**锛歚rollback` 浠呭湪銆岀‘瀹炲紑濮嬭繃閮ㄧ讲鍙樻洿銆嶏紙`deploy_attempted == 'true'`锛変笖娴佹按绾垮け璐ユ椂鎵ц銆?
  - SSH 瀹屽叏涓嶅彲杈俱€佸皻鏈敼鍔ㄤ换浣曟湇鍔℃椂锛坄deploy_attempted != 'true'`锛?*涓嶈Е鍙戝洖婊?*銆?
  - 闀滃儚鎷夊彇/閲嶅惎瓒呮椂銆佹垨閮ㄧ讲鍚庨獙璇佸け璐ユ椂**瑙﹀彂鍥炴粴**銆?
- **涓嶅彲鍙樻爣绛句繚鎶?*锛歚build-push` 鎺ㄩ€佸墠浼氭鏌ョ洰鏍?SHA 鏍囩鏄惁宸插瓨鍦ㄤ簬 GHCR锛屽瓨鍦ㄥ垯浣滀笟澶辫触銆佺粷涓嶈鐩栥€?

---

## 3. 鎵€闇€ GitHub Secrets 娓呭崟

鍦?GitHub 浠撳簱 `Settings 鈫?Secrets and variables 鈫?Actions` 涓厤缃互涓?Secret锛?

| Secret 鍚嶇О | 鏄惁蹇呴渶 | 璇存槑 |
|-------------|----------|------|
| `SSH_HOST` | 蹇呴渶 | 鐢熶骇鏈嶅姟鍣ㄤ富鏈哄悕鎴?IP |
| `SSH_USER` | 蹇呴渶 | SSH 鐧诲綍鐢ㄦ埛鍚?|
| `SSH_KEY` | 蹇呴渶 | SSH 绉侀挜锛堢敤浜?`appleboy/ssh-action` 鍏嶅瘑鐧诲綍锛?|
| `SSH_PORT` | 鍙€?| SSH 绔彛锛岀己鐪佷负 22 |
| `AUS_ELE_JWT_SECRET` | 蹇呴渶 | 鍚庣 JWT 绛惧悕瀵嗛挜锛堢敓鎴愶細`python -c "import secrets; print(secrets.token_hex(32))"`锛?|
| `FINGRID_API_KEY` | 蹇呴渶 | Fingrid 鏁版嵁鎺ュ彛 API Key |

> **GHCR 璁よ瘉鏃犻渶棰濆 Secret**锛歚build-push` 浣滀笟澶嶇敤 GitHub Actions 鍐呯疆鐨?`GITHUB_TOKEN`锛堥渶鍦?workflow 涓巿浜?`packages: write` 鏉冮檺锛夌櫥褰?`ghcr.io`锛屽嚟璇佺敱 Action 鑷姩灞忚斀锛屼笉浼氬洖鏄俱€?

> **Secret 鍓嶇疆鏍￠獙**锛歚deploy` 浣滀笟绗竴姝ヤ細鍦?runner 涓婃牎楠屼笂杩板繀闇€ Secret 鏄惁瀛樺湪涓旈潪绌猴紝浠讳竴缂哄け浼氬湪浠讳綍 SSH / 鎷夊彇 / 閲嶅惎鍔ㄤ綔**涔嬪墠**绔嬪嵆澶辫触锛屼笖鍙姤鍛婄己澶辩殑**鍚嶇О**銆佺粷涓嶈緭鍑哄€笺€?

---

## 4. 鐢熶骇鏈嶅姟鍣ㄥ墠缃噯澶?

閮ㄧ讲鐩爣涓鸿嚜鎵樼鍗曟満锛岃矾寰勭害瀹氫负 `/www/wwwroot/aus-ele`銆傞娆″惎鐢ㄦ祦姘寸嚎鍓嶉渶瀹屾垚浠ヤ笅鍑嗗锛?

### 4.1 瀹夎杩愯鏃朵緷璧?

- 瀹夎 Docker 涓?Docker Compose 鎻掍欢锛坄docker compose` v2 璇硶锛夈€?
- 纭鎵ц閮ㄧ讲鐨?SSH 鐢ㄦ埛鍦?`docker` 鐢ㄦ埛缁勫唴锛屽彲鍏?sudo 杩愯 docker 鍛戒护銆?

### 4.2 鍏嬮殕浠撳簱

```bash
sudo mkdir -p /www/wwwroot/aus-ele
sudo chown "$USER" /www/wwwroot/aus-ele
git clone <浠撳簱鍦板潃> /www/wwwroot/aus-ele
```

閮ㄧ讲鑴氭湰浼氬湪姣忔閮ㄧ讲鏃?`git fetch && git checkout <SHA>`锛屼娇鏈嶅姟鍣ㄤ笂鐨?`docker-compose.prod.yml` 涓庨儴缃茶剼鏈缁堜笌鍙戝竷鐗堟湰涓€鑷淬€?

### 4.3 鍑嗗 `.env.prod`

鍦?`/www/wwwroot/aus-ele/.env.prod` 鍐欏叆杩愯鏃跺彉閲忥紙鍙弬鑰冧粨搴撴牴 `.env.docker.example`锛夛紝骞惰缃弗鏍兼潈闄愶細

```bash
chmod 600 /www/wwwroot/aus-ele/.env.prod
```

> 閮ㄧ讲鏃舵祦姘寸嚎浼氬皢瀵嗛挜涓?`IMAGE_TAG` 鍐欏叆璇ユ枃浠躲€俙.env.prod` **涓嶇撼鍏ヤ粨搴撹拷韪?*锛堣绗?6 鑺傦級锛屼笖寮哄埗 `chmod 600`銆?

### 4.4 棣栨閮ㄧ讲鐨勭壒娈婃儏鍐?

- 棣栨閮ㄧ讲鏃舵湇鍔″櫒涓?*灏氭棤 `state/last_stable_tag`**锛堟棤绋冲畾鐗堟湰璁板綍锛夈€?
- 鑻ラ娆￠儴缃插嵆瑙﹀彂鍥炴粴锛堜緥濡傞獙璇佸け璐ワ級锛岀敱浜庢病鏈夊彲鍥炴粴鐨勭ǔ瀹?SHA锛?*鍥炴粴浼氳璺宠繃銆佷綔涓氫互澶辫触缁撴潫骞舵姤鍛娿€屾棤鍙洖婊氱増鏈€?*锛岄渶浜哄伐浠嬪叆鎺掓煡銆?
- 寤鸿棣栨閮ㄧ讲鍦ㄤ綆宄版湡杩涜锛屽苟纭 Health/Smoke 閫氳繃鍚庡啀渚濊禆鑷姩娴佺▼銆?

---

## 5. 閮ㄧ讲鍚庨獙璇佷笌澶辫触鑷姩鍥炴粴鏈哄埗

### 5.1 閮ㄧ讲鍚庨獙璇侊紙verify 浣滀笟锛?

閮ㄧ讲鎴愬姛鍚庯紝`verify` 浣滀笟缁?SSH 鍦ㄦ湇鍔″櫒鎵ц `deploy/scripts/verify.sh`锛?

1. **Health_Check**锛氭帰娴?`http://127.0.0.1:<API_HOST_PORT>/api/health`
   - 鍗曟瓒呮椂 10s銆佹渶澶?10 娆°€侀棿闅?5s銆佹€荤獥鍙?60s銆?
2. **Smoke_Test**锛欻ealth 閫氳繃鍚庤繍琛屾牴鐩綍 `smoke_test_api.py`
   - 閫氳繃 `SMOKE_BASE_URL` 鐜鍙橀噺鎸囧悜鐢熶骇鍦板潃銆?
   - 璇勪及鏍囧噯锛氭墍鏈夎娴嬬鐐瑰潎鏃?500銆佹棤杩炴帴澶辫触 鈫?閫氳繃锛涘惁鍒欏け璐ャ€?
3. **璁板綍绋冲畾鐗堟湰**锛氶獙璇侀€氳繃鍚庯紝灏嗘湰娆￠儴缃?SHA 鍐欏叆 `/www/wwwroot/aus-ele/state/last_stable_tag`锛屼綔涓哄悗缁洖婊氱洰鏍囥€?

### 5.2 澶辫触鑷姩鍥炴粴锛坮ollback 浣滀笟锛?

褰?`deploy` 鎴?`verify` 澶辫触涓?`deploy_attempted == 'true'` 鏃讹紝瑙﹀彂 `rollback` 浣滀笟锛屾墽琛?`deploy/scripts/rollback.sh`锛?

- 璇诲彇 `state/last_stable_tag`锛?
  - **涓嶅瓨鍦?/ 涓虹┖ / 闈炴硶**锛堥娆￠儴缃茬瓑锛夆啋 璺宠繃鍥炴粴锛屼綔涓氬け璐ワ紝鎶ュ憡銆屾棤鍙洖婊氱増鏈€嶃€?
  - **瀛樺湪鍚堟硶 SHA** 鈫?浠ヨ SHA 璁句负 `IMAGE_TAG`锛屾媺鍙栧苟閲嶅惎 backend/worker/web銆?
- 鍥炴粴鍚庡啀娆℃墽琛?Health_Check锛堟渶澶?5 娆°€侀棿闅?10s銆佹€荤獥鍙?60s锛夛細
  - **鎴愬姛** 鈫?娴佹按绾夸互澶辫触缁撴潫锛屾姤鍛娿€屽凡鍥炴粴鍒?`<Last_Stable_Tag>`銆嶃€?
  - **澶辫触** 鈫?娴佹按绾夸互澶辫触缁撴潫锛屾姤鍛娿€屽洖婊氬け璐ラ渶浜哄伐浠嬪叆銆嶏紝淇濈暀褰撳墠鐘舵€佷互渚挎帓鏌ャ€?
- 瑙﹀彂鍥炴粴鐨勫け璐ラ」锛圚ealth 鎴?Smoke锛変笌鍥炴粴鐩爣 SHA 鍧囧啓鍏ユ棩蹇椼€?

### 5.3 鍙娴嬫€?

姣忎釜浣滀笟鏈熬鍚?`$GITHUB_STEP_SUMMARY` 鍐欏叆闃舵鐘舵€侊紙`鎴愬姛 / 澶辫触 / 璺宠繃` 涓夋€侊級锛屽け璐ユ楠ゅ悕涓庨敊璇俊鎭緭鍑哄埌鏃ュ織锛汫itHub Actions 鏃ュ織榛樿淇濈暀 鈮?0 澶┿€?

---

## 6. `docker-compose.prod.yml` 涓?`.env.prod` 鐨勫叧绯?

| 宸ヤ欢 | 鏄惁杩借釜 | 浣滅敤 |
|------|----------|------|
| `docker-compose.prod.yml` | **杩借釜**锛堜粨搴撳唴锛?| 鐢熶骇缂栨帓鏂囦欢銆俠ackend/worker/web 鏀逛负 `image: ${REGISTRY}/${IMAGE_PREFIX}/<svc>:${IMAGE_TAG}` 鎸?SHA 鎷夊彇 GHCR 棰勬瀯寤洪暅鍍忥紝涓嶅湪鐢熶骇鏈烘湰鍦版瀯寤恒€?|
| `/www/wwwroot/aus-ele/.env.prod` | **涓嶈拷韪?*锛坄chmod 600`锛?| 鎻愪緵 compose 鍙橀噺鏇挎崲鎵€闇€杩愯鏃跺€硷細`REGISTRY`銆乣IMAGE_PREFIX`銆乣IMAGE_TAG`銆乣API_HOST_PORT`銆乣WEB_HOST_PORT`銆乣AUS_ELE_JWT_SECRET`銆乣FINGRID_API_KEY` 绛夈€?|

杩愯鏃跺叧绯伙細

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

- compose 鏂囦欢涓殑 `${IMAGE_TAG}`銆乣${REGISTRY}` 绛夊崰浣嶇敱 `.env.prod` 娉ㄥ叆锛屼粠鑰岃鍚屼竴浠界敓浜?compose 鍙寚鍚戜换鎰?commit SHA 闀滃儚锛涢儴缃蹭笌鍥炴粴浠呭垏鎹?`IMAGE_TAG` 鍗冲彲銆?
- 浠撳簱 `.gitignore` 宸查€氳繃 `.env.*` + `!*.example` 璐熷悜瑙勫垯锛岀‘淇?`.env`銆乣.env.prod` 绛夋晱鎰熸枃浠朵笉琚拷韪紝鑰?`.env.example`銆乣.env.docker.example` 绀轰緥鏂囦欢淇濇寔杩借釜銆?

---

## 7. 鐩稿叧鏂囦欢绱㈠紩

| 鏂囦欢 | 璇存槑 |
|------|------|
| `.github/workflows/ci.yml` | CI/CD 娴佹按绾垮畾涔夛紙6 浣滀笟锛?|
| `docker-compose.prod.yml` | 鐢熶骇缂栨帓锛堟寜 `IMAGE_TAG` 鎷夊彇 GHCR 闀滃儚锛?|
| `.env.docker.example` | 鐜鍙橀噺绀轰緥锛堝惈 `REGISTRY`/`IMAGE_PREFIX`/`IMAGE_TAG` 鍗犱綅锛?|
| `deploy/scripts/deploy.sh` | 鏈嶅姟鍣ㄤ晶锛氬啓 env銆佹鍑恒€乸ull銆乽p銆佺‘璁?running |
| `deploy/scripts/verify.sh` | Health 閲嶈瘯 + 杩愯 `smoke_test_api.py` |
| `deploy/scripts/rollback.sh` | 璇诲彇骞堕噸閮ㄧ讲 Last_Stable_Tag |
| `smoke_test_api.py` | 鍐掔儫娴嬭瘯鑴氭湰锛堟敮鎸?`SMOKE_BASE_URL` 瑕嗙洊銆佹寜缁撹杩斿洖閫€鍑虹爜锛?|

