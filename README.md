# 每週匹克球預約流程

本機 Codex 排程搭配內建瀏覽器、自動登入、訂場確認及 Gmail 待付款通知。網站：<https://fe.xuanen.com.tw/>。

每週六台灣時間00:00開始，訂七天後週六15–16與16–17各一面。同場優先；任一時段沒有空場則不開始訂部分時段，兩小時合計不超過NT$900。兩張訂單分別建立，第二張仍可能因搶場或網站錯誤失敗；不會自動取消第一張。只建立待付款訂單，由使用者於每張訂單建立後10分鐘內付款。

## 已驗證與限制

2026/10/25在真實網站完成自動登入、兩個預約確認視窗自動接受、兩筆待付款訂單核對及SMTP接受付款通知。每週排程喚醒時間尚未實測，可能延遲。遇網站人機驗證、額外條款或訂單結果不明時停止並通知，不能保證永遠不需人工。

**主要流程必須使用本機Codex內建瀏覽器，電腦開機、連網且Codex開啟。這不是上傳GitHub就能自動在雲端訂場的服務。**

儲存庫原本的 `runner.py`、`planner.py`、`settings.json` 與GitHub Actions為早期雲端「只查場」版本，不能建立預約，網站驗證未通過。`chrome_runner.py`為獨立Chrome實驗版本，也未通過真實網站驗證。現行排程不執行這兩個版本，不要將其測試成功當作內建瀏覽器流程結果。

## 本機設定（Windows）

需要Python、Node.js及支援內建瀏覽器操作的Codex。

```powershell
Copy-Item config.example.json config.json
python login_credentials.py --setup
python send_notice.py --setup
```

先在 `config.json` 填入寄件Gmail與收件信箱，再執行上述設定。Gmail使用應用程式密碼；輸入均在本機終端機遮蔽，不貼到聊天或GitHub。設定完成、核對預約條件後才把 `enabled` 改成 `true`。

球場及Gmail憑證透過Windows目前使用者DPAPI加密，保存在 `%LOCALAPPDATA%/XuanenCourtBot/`，不在儲存庫。換電腦或Windows使用者要重新設定。既有已設定電腦不需重設，也不要覆蓋其config.json。

## 執行方式

完整流程在 [WORKFLOW.md](WORKFLOW.md)，排程設定範本在 [SCHEDULER.md](SCHEDULER.md)。排程屬於Codex本機設定，不會因clone儲存庫自動建立。

`auto_login.mjs`、`confirm_booking.mjs`必須從Codex瀏覽器JavaScript工具匯入，傳入受支援的tab物件；不是直接以Node啟動即可訂場。不得讀出或列印帳密。

確認視窗的關鍵：點擊和接收 `getJsDialog()` 必須並行，不能先等待click結束再處理確認。模組只點一次，回傳已接受確認後還須等待成功頁，再核對我的訂單。

## 測試

```powershell
node --test test_auto_login.mjs test_confirm_booking.mjs
```

11項主要模組測試，涵蓋錯誤網域、登入失敗清空、不重試、並行確認及價格/頁面核對。測試使用合成資料，不連球場、不寄信、不建立預約。

獨立Chrome實驗另有7項測試（需安裝requirements及本機Chrome）：

```powershell
python -m pip install -r requirements.txt
python -m unittest test_chrome_runner.py -v
```

## 檔案

- `config.example.json`：無個人資料的設定範本。
- `login_credentials.py`、`auto_login.mjs`：加密保存及自動登入。
- `confirm_booking.mjs`：核對場號時段及原生確認視窗。
- `core.py`、`send_notice.py`：配對、時區及Gmail通知。
- `WORKFLOW.md`、`SCHEDULER.md`：網站完整流程與本機排程範本。

不提交本機config、憑證、cookies、瀏覽器設定檔、訂單紀錄、個人截圖或追蹤資料。
