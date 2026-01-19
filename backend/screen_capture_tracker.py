"""
Macの画面をリアルタイムでキャプチャして物体を追跡するスクリプト

機能:
- mssを使って画面をリアルタイムキャプチャ
- ウィンドウを選択してキャプチャ可能（ターミナル除外）
- YOLOv12で物体を追跡（ID維持）
- 赤い枠（穴あき長方形）を検出（red_tracking_utilsを使用）
- 物体が赤い枠の開口部を通過したかを判定・記録
- トラックバーでHSVパラメータをリアルタイム調整可能
"""

import cv2
import numpy as np
import threading
import asyncio
from ultralytics import YOLO
import red_tracking_utils as utils
import websocket_server

try:
    import mss
except ImportError:
    print("mssがインストールされていません。以下のコマンドでインストールしてください:")
    print("  uv add mss")
    exit(1)

try:
    import Quartz
except ImportError:
    print("PyObjCがインストールされていません。以下のコマンドでインストールしてください:")
    print("  uv add pyobjc-framework-Quartz")
    exit(1)


def get_windows(exclude_terminal=True):
    """利用可能なウィンドウの一覧を取得"""
    # ターミナル関連のアプリ名
    terminal_apps = ['Terminal', 'iTerm2', 'iTerm', 'Hyper', 'Alacritty', 'kitty', 'Warp', 'Code', 'Cursor']

    windows = []
    window_list = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID
    )

    for window in window_list:
        owner = window.get('kCGWindowOwnerName', '')
        name = window.get('kCGWindowName', '')
        bounds = window.get('kCGWindowBounds', {})

        # サイズが小さすぎるウィンドウは除外
        if bounds.get('Width', 0) < 100 or bounds.get('Height', 0) < 100:
            continue

        # ターミナルを除外
        if exclude_terminal and owner in terminal_apps:
            continue

        # 名前がないウィンドウは除外（メニューバーなど）
        if not name and not owner:
            continue

        windows.append({
            'owner': owner,
            'name': name,
            'bounds': bounds,
            'id': window.get('kCGWindowNumber', 0)
        })

    return windows


def select_window():
    """ウィンドウを選択する"""
    windows = get_windows(exclude_terminal=True)

    if not windows:
        print("キャプチャ可能なウィンドウが見つかりませんでした。")
        return None

    print("\n" + "=" * 60)
    print("ウィンドウ選択")
    print("=" * 60)
    print("キャプチャするウィンドウを選択してください:")
    print("  0: 画面全体")

    for i, win in enumerate(windows, 1):
        name = win['name'] or '(無題)'
        bounds = win['bounds']
        size = f"{int(bounds['Width'])}x{int(bounds['Height'])}"
        print(f"  {i}: [{win['owner']}] {name} ({size})")

    print("=" * 60)

    while True:
        try:
            choice = input("番号を入力 (0で全画面): ").strip()
            if choice == '':
                choice = 0
            else:
                choice = int(choice)

            if choice == 0:
                return None  # 全画面
            elif 1 <= choice <= len(windows):
                return windows[choice - 1]
            else:
                print(f"1から{len(windows)}の番号を入力してください。")
        except ValueError:
            print("数字を入力してください。")
        except KeyboardInterrupt:
            print("\nキャンセルしました。")
            return None


def run_websocket_server():
    """WebSocket サーバーを別スレッドで実行"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(websocket_server.start_server())


def main():
    # WebSocket サーバーを別スレッドで起動
    ws_thread = threading.Thread(target=run_websocket_server, daemon=True)
    ws_thread.start()

    # YOLOv12のモデルをロード
    model = YOLO("yolo12n.pt")

    # mssでスクリーンキャプチャを初期化
    sct = mss.mss()

    # ウィンドウを選択
    selected_window = select_window()

    if selected_window:
        # 選択したウィンドウの領域
        bounds = selected_window['bounds']
        capture_region = {
            'left': int(bounds['X']),
            'top': int(bounds['Y']),
            'width': int(bounds['Width']),
            'height': int(bounds['Height'])
        }
        print(f"\n選択したウィンドウ: [{selected_window['owner']}] {selected_window['name'] or '(無題)'}")
    else:
        # 全画面
        capture_region = sct.monitors[1]
        print("\n画面全体をキャプチャします。")

    print(f"キャプチャ領域: {capture_region}")
    print(f"解像度: {capture_region['width']}x{capture_region['height']}")

    # HSVトラックバーを作成（調整モード時のみ）
    if utils.ENABLE_TUNING:
        utils.create_trackbars()

    # 通過追跡器
    tracker = utils.CrossingTracker()

    frame_count = 0

    print("\n" + "=" * 50)
    print("画面キャプチャ版 赤い枠通過トラッカー")
    print("=" * 50)
    print("- mssを使用して画面をリアルタイムキャプチャ")
    print("- 赤い抽出マスクを生で表示します（ノイズ処理なし）")
    if utils.ENABLE_TUNING:
        print("- [調整モード] HSV Controlsウィンドウでパラメータを調整できます")
    else:
        print("- [通常モード] 固定されたパラメータで動作します")
        print("  パラメータを調整したい場合は red_tracking_utils.py の ENABLE_TUNING を True にしてください")
    print("- 'q' または ESC で終了")
    print("=" * 50)

    try:
        while True:
            # 画面をキャプチャ
            screenshot = sct.grab(capture_region)

            # mssの画像をOpenCV形式（BGR）に変換
            # mssはBGRA形式で返すので、BGRに変換
            frame = np.array(screenshot)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            # パフォーマンス向上のためリサイズ（オプション）
            # 大きな画面の場合は処理が重くなるので、必要に応じてリサイズ
            scale_factor = 1.0  # 1.0 = オリジナルサイズ、0.5 = 半分
            if scale_factor != 1.0:
                frame = cv2.resize(frame, None, fx=scale_factor, fy=scale_factor)

            frame_count += 1

            # トラックバーからHSVパラメータを更新（調整モード時のみ）
            if utils.ENABLE_TUNING:
                utils.update_hsv_params()

            # 赤い枠の検出（マスク生成）
            mask = utils.red_mask_hsv(frame)

            # 枠（穴あき）検出
            red_frames = utils.detect_red_frames(mask)

            # YOLO物体追跡
            results = model.track(frame, persist=True, verbose=False)

            # 描画用フレーム
            annotated_frame = results[0].plot()

            # 赤い枠を描画
            for rf in red_frames:
                cv2.drawContours(annotated_frame, [rf["outer_contour"]], -1, (0, 255, 0), 2)
                if rf["inner_contour"] is not None:
                    cv2.drawContours(annotated_frame, [rf["inner_contour"]], -1, (255, 0, 0), 2)
                cv2.drawMarker(annotated_frame, rf["center"], (0, 255, 255),
                              markerType=cv2.MARKER_CROSS, thickness=2, markerSize=20)

            # 各物体の通過判定
            if results[0].boxes is not None and results[0].boxes.id is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy()
                ids = results[0].boxes.id.cpu().numpy().astype(int)
                clss = results[0].boxes.cls.cpu().numpy().astype(int)

                for box, obj_id, cls_id in zip(boxes, ids, clss):
                    obj_name = model.names[cls_id]

                    # 通過判定
                    crossed = tracker.update(obj_id, box, red_frames)

                    if crossed:
                        print(f"物体 ID={obj_id} ({obj_name}) が赤い枠を通過しました！（累計: {tracker.crossing_counts[obj_id]}回）")
                        # WebSocket で通知
                        websocket_server.send_crossing_event(
                            object_id=int(obj_id),
                            object_name=obj_name,
                            crossing_count=tracker.crossing_counts[obj_id]
                        )

                    # 物体の通過回数を表示
                    count = tracker.crossing_counts[obj_id]
                    if count > 0:
                        cv2.putText(annotated_frame, f"ID:{obj_id} {obj_name} x{count}",
                                   (int(box[0]), int(box[1]) - 10),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            # 全体統計を画面に表示
            cv2.rectangle(annotated_frame, (10, 10), (300, 130), (0, 0, 0), -1)
            cv2.putText(annotated_frame, f"Crossings: {tracker.get_total_crossings()}",
                       (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(annotated_frame, f"Red Frames: {len(red_frames)}",
                       (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
            cv2.putText(annotated_frame, f"Frame: {frame_count}",
                       (20, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            # 現在のHSVパラメータを表示
            hsv_params = utils.hsv_params
            cv2.putText(annotated_frame, f"H:{hsv_params.h1_low}-{hsv_params.h1_high}/{hsv_params.h2_low}-{hsv_params.h2_high}",
                       (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # ウィンドウに表示
            cv2.imshow("Screen Capture Tracker", annotated_frame)
            cv2.imshow("Red Mask", mask)

            # 終了判定
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), 27):
                break

    except KeyboardInterrupt:
        print("\nキーボード割り込みで終了")

    # 最終統計を表示
    print("\n" + "=" * 50)
    print("最終統計")
    print("=" * 50)
    print(f"総通過回数: {tracker.get_total_crossings()}")
    print(f"処理フレーム数: {frame_count}")
    if utils.ENABLE_TUNING:
        hsv_params = utils.hsv_params
        print("\n最終HSVパラメータ:")
        print(f"  H1: {hsv_params.h1_low} - {hsv_params.h1_high}")
        print(f"  H2: {hsv_params.h2_low} - {hsv_params.h2_high}")
        print(f"  S:  {hsv_params.s_low} - {hsv_params.s_high}")
        print(f"  V:  {hsv_params.v_low} - {hsv_params.v_high}")
    print("=" * 50)

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
