# 雲端測試結果（2026/10/24，Asia/Taipei）

正確私人儲存庫：https://github.com/austenjuan2222/court-booking-bot

五項必要 Secrets 均已由使用者輸入或確認儲存。未讀出 Secret 內容。

## 已通過

- GitHub Ubuntu runner、Python 與 Chromium 安裝。
- 4 項場地配對與金額上限測試。
- 使用 GitHub Secrets 內的 Gmail 憑證寄失敗通知，SMTP 接受成功。

## 未通過

- 第一次：登入提交後未確認登入成功。
- 第二次：延長等待並分類錯誤，網站顯示驗證失敗。
- 第三次：先被動等待網站自己的 Turnstile 驗證結果 45 秒，驗證仍未自動完成，程式依規則停止。沒有解題、偽造驗證結果或繞過驗證。

第三次執行：https://github.com/austenjuan2222/court-booking-bot/actions/runs/40107647227

因此尚未確認帳密是否通過網站驗證，也未能進入登入後的雲端查場。沒有建立訂單、取消訂單或付款。

GitHub 每週查場變數 ENABLE_CLOUD_PREVIEW 未啟用；正式雲端訂場未實作、未啟用。原本的本機 Codex 排程仍保留，不能將其視為雲端方案。

目前不能宣稱已完成完全無人登入的雲端訂場。需要網站提供可用的官方登入整合、允許的自動化方法，或重新評估其他執行環境；更換付費主機也不保證能通過網站驗證。
