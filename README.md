# 匹克球雲端自動登入測試版

此版本先驗證 GitHub Actions 的 Linux 雲端環境能否自動登入網站、查場及寄信。**不建立預約、不付款，也不是已完成的雲端訂場機器人。** 真正下單流程尚待驗證與實作。原本的本機 Codex 排程尚未遷移或關閉。

## 設定

在 austenjuan2222 帳號下新建私人儲存庫 court-booking-bot，將此資料夾內容放在儲存庫根目錄。不要上傳本機 DPAPI 憑證或任何密碼。

在 Settings → Secrets and variables → Actions 新增五項 Repository secrets：

| 名稱 | 內容 |
|---|---|
| COURT_USER | 球場會員登入帳號 |
| COURT_PASSWORD | 球場網站密碼 |
| GMAIL_USER | austenjuan2@gmail.com |
| GMAIL_APP_PASSWORD | Gmail 應用程式密碼 |
| NOTIFY_EMAIL | austenjuan2@gmail.com |

然後 Actions → Cloud login and court preview → Run workflow。這次只測試登入、查場與寄信。請勿將密碼填入程式碼、Issue 或聊天。

每週排程預設不執行；只有設 repository variable ENABLE_CLOUD_PREVIEW=true 才開始每週查場測試。請先手動測試通過，不必先開排程。GitHub 排程可能延遲，沒有準點搶場保證。這個版本每次執行重新登入，不儲存 cookies 或瀏覽器狀態；若網站需要驗證碼或封鎖雲端 IP，測試會失敗並嘗試寄信通知，不會繞過驗證。

## 費用

使用標準 Ubuntu runner，沒有雲端主機訂閱。私人儲存庫會使用帳號的 Actions 免費額度，若帳號已有其他專案，仍須查看總用量；不能承諾所有情況零費用。請在 GitHub Billing 確認可用額度與支出限制，不啟用付費 runner。

## 驗證狀態

本機已測試同場優先、價格上限、排除已訂場地與不訂部分時段的規則。五項雲端 Secrets 已設定，已執行三次雲端登入測試。Gmail 失敗通知成功；網站登入驗證未能在雲端自動完成（最後一次被動等待45秒仍無結果），所以雲端登入與查場尚未通過。每週雲端測試未啟用，沒有建立預約。詳見 CLOUD-TEST-RESULT.md。網站登入欄位與查場清單來自實際觀察。請以雲端測試結果判斷能否繼續做無人訂場，不能用本機登入成功推定雲端也成功。
