# English 800｜職場有聲英文 PWA v2

iPhone 加到主畫面使用的英文學習 App（GitHub Pages 部署）。

## v2 新功能
- **自動連播＋自動切下一課**：英文 → 中文 → 慢速 → 關鍵片語，播完自動標記完成並接下一課；可設定重複次數、速度、略過已完成。
- **商務課程擴充到 45 篇**：郵件、會議、談判、財報、供應鏈、行銷、人資、客服、簡報、科技業、經濟新聞、出差、專案管理。
- **每日美國商業新聞**：GitHub Actions 每天台灣時間 06:10 抓 NPR / CNBC / NYT / MarketWatch / Yahoo Finance 的 RSS，自動轉成新聞課程（含關鍵字彙、中文翻譯、測驗題）。保留最近 7 天。
- **真人級語音 MP3**：Actions 用 edge-tts（微軟神經語音）幫每課與每則新聞產生 MP3。
- **駕駛模式／CarPlay**：大按鈕介面；音檔模式支援鎖定畫面、藍牙、CarPlay「播放中」的 ⏮ ⏭ 換課。
- 測驗題自動由課程與新聞產生、連續學習天數、單字庫自動收錄片語與新聞字彙。

## 部署步驟（第一次）
1. 把本資料夾**所有檔案**（包含隱藏資料夾 `.github/`）上傳到你的 GitHub repo 根目錄，覆蓋舊版。
   - Mac Finder 看不到 `.github` 時按 `⌘ + Shift + .` 顯示隱藏檔。
   - 或在 GitHub 網頁按 **Add file → Create new file**，檔名輸入 `.github/workflows/daily-update.yml`，貼上內容。
2. repo **Settings → Actions → General → Workflow permissions** 選 **Read and write permissions** → Save。
3. **Actions** 分頁 → 左側「Daily news & audio update」→ **Run workflow**。約 5–10 分鐘後會產生 `data/news.json`、`data/audio.json` 和 `audio/*.mp3`。
4. GitHub Pages 會自動重新部署。iPhone 開啟 App（建議完全關閉再開一次以載入新版）。

之後每天早上自動更新，不用再動手。修改 `data/lessons.json` 推上去也會自動重新產生音檔。

## 檔案結構
```
index.html               App 主程式
sw.js                    離線快取（音檔不快取以支援串流）
manifest.webmanifest
data/lessons.json        商務課程（可自行增加）
data/news.json           每日新聞（自動產生）
data/audio.json          音檔對照表（自動產生）
audio/*.mp3              語音檔（自動產生）
scripts/build_news.py    抓新聞 RSS
scripts/build_audio.py   產生 MP3
.github/workflows/daily-update.yml
```

## 關於 CarPlay
Apple 只開放原生 App（需 Apple 核准的 CarPlay 權限）出現在 CarPlay 主畫面，網頁 App 無法有自己的 CarPlay 圖示。本版做法：
- iPhone 連 CarPlay 後在 App 按播放，聲音從車上喇叭出來，CarPlay「播放中」會顯示課程名稱，可用螢幕或方向盤 ⏮ ⏭ 切換課程（音檔模式）。
- 系統語音模式（沒有 MP3 時的備援）只能在 App 前景播放，鎖屏會停。

## 注意事項
- 新聞內容為各媒體 RSS 的標題與摘要，附原文連結，版權屬原媒體，僅供個人學習使用。
- 中文翻譯使用免費翻譯端點，偶爾失敗時 App 會提供 Google 翻譯連結。
- edge-tts 為非官方套件；若某天失效，App 會自動改用 iPhone 系統語音。
- 學習紀錄存在本機 localStorage，不會跨裝置同步。
