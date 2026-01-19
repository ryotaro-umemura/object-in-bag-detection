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

## 設定フラグ

### 表示設定（main.py）

```python
SHOW_TRACKER_WINDOW = True   # メイントラッカー画面を表示
SHOW_MASK_WINDOW = False     # 赤マスク（白黒）画面を表示
```

| フラグ                | 説明                                 |
| --------------------- | ------------------------------------ |
| `SHOW_TRACKER_WINDOW` | YOLO検出結果のメインウィンドウを表示 |
| `SHOW_MASK_WINDOW`    | 赤色抽出マスク（デバッグ用）を表示   |

### HSV チューニング（red_tracking_utils.py）

```python
ENABLE_TUNING = False  # True: パラメータ調整モード
```

`True` にするとトラックバーが表示され、赤色検出のHSVパラメータをリアルタイムで調整可能。照明環境に合わせて調整後、最適な値をコードに反映してください。

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
