# Object in Bag Detection

赤い枠を通過した物体をリアルタイムで検出・表示するシステム

## 概要

- **Backend**: YOLOv12 で画面をキャプチャし、赤い枠を通過した物体を検出
- **Frontend**: WebSocket で通過情報を受け取り、ブラウザにリアルタイム表示

---

## セットアップ

### Backend

```bash
cd backend
uv sync
```

### Frontend

```bash
cd frontend
pnpm install
```

---

## 起動方法

### 1. Backend を起動

```bash
cd backend
uv run python main.py
```

起動前に `main.py` の `TARGET_WINDOW_NAME` を編集してキャプチャ対象を指定：

```python
TARGET_WINDOW_NAME = "Chrome"  # ウィンドウ名（部分一致）
```

### 2. Frontend を起動

```bash
cd frontend
pnpm run dev
```

ブラウザで http://localhost:3000 を開く

---

## 使い方

1. 赤い枠（紙などで作成）を画面に配置
2. 物体を赤い枠に通過させる
3. 通過した物体がブラウザにカードとして表示される

---

## 動作確認

| 表示         | 状態                           |
| ------------ | ------------------------------ |
| 🟢 接続済み  | Backend と正常に接続中         |
| 🟡 接続中... | 接続を試みている               |
| 🔴 切断      | Backend が停止中（自動再接続） |

---

## 終了方法

- Backend: `q` キーまたは `ESC` で終了
- Frontend: `Ctrl+C` で終了
