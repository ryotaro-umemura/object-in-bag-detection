"""
赤い枠を通過する物体をリアルタイムで追跡するスクリプト（メイン）

機能:
- YOLOv11で物体を追跡（ID維持）
- 赤い枠（穴あき長方形）を検出（red_tracking_utilsを使用）
- 物体が赤い枠の開口部を通過したかを判定・記録
- トラックバーでHSVパラメータをリアルタイム調整可能
- Quartzを使用してウィンドウをリアルタイムキャプチャ
"""

import cv2
import numpy as np
import threading
import asyncio
import Quartz.CoreGraphics as CG
from ultralytics import YOLO
import red_tracking_utils as utils
import websocket_server

# キャプチャ対象のウィンドウ名（部分一致）
TARGET_WINDOW_NAME = "Chrome"

# 表示設定フラグ
SHOW_TRACKER_WINDOW = True
SHOW_MASK_WINDOW = False


def find_window_id(window_name_part):
    """指定した名前を含むウィンドウのIDを検索する"""
    options = CG.kCGWindowListOptionOnScreenOnly
    window_list = CG.CGWindowListCopyWindowInfo(options, CG.kCGNullWindowID)

    for window in window_list:
        owner_name = window.get('kCGWindowOwnerName', '')
        win_name = window.get('kCGWindowName', '')

        if window_name_part.lower() in owner_name.lower() or \
           window_name_part.lower() in win_name.lower():
            return window['kCGWindowNumber'], owner_name, win_name

    return None, None, None


def capture_window(window_id):
    """ウィンドウをキャプチャしてnumpy配列として返す"""
    image_ref = CG.CGWindowListCreateImage(
        CG.CGRectNull,
        CG.kCGWindowListOptionIncludingWindow,
        window_id,
        CG.kCGWindowImageBoundsIgnoreFraming | CG.kCGWindowImageNominalResolution
    )

    if image_ref is None:
        return None

    width = CG.CGImageGetWidth(image_ref)
    height = CG.CGImageGetHeight(image_ref)
    bytes_per_row = CG.CGImageGetBytesPerRow(image_ref)

    provider = CG.CGImageGetDataProvider(image_ref)
    data = CG.CGDataProviderCopyData(provider)

    try:
        np_data = np.frombuffer(data, dtype=np.uint8)
        expected_len = width * height * 4

        if len(np_data) == expected_len:
            img = np_data.reshape((height, width, 4))
        else:
            row_len = width * 4
            if len(np_data) >= height * bytes_per_row:
                img_padded = np_data[:height*bytes_per_row].reshape((height, bytes_per_row))
                img = img_padded[:, :row_len].reshape((height, width, 4))
            else:
                return None

        # アルファチャンネルを削除してBGR形式に変換
        img_bgr = img[:, :, :3]
        return img_bgr

    except Exception as e:
        print(f"フレーム処理エラー: {e}")
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

    # ウィンドウIDを検索
    window_id, owner, title = find_window_id(TARGET_WINDOW_NAME)
    if window_id is None:
        raise RuntimeError(f"'{TARGET_WINDOW_NAME}'を含むウィンドウが見つかりませんでした。TARGET_WINDOW_NAMEを変更してください。")

    # HSVトラックバーを作成（調整モード時のみ）
    if utils.ENABLE_TUNING:
        utils.create_trackbars()

    # 通過追跡器
    tracker = utils.CrossingTracker()

    frame_count = 0

    print("=" * 50)
    print("赤い枠通過トラッカー（ウィンドウキャプチャ版）")
    print("=" * 50)
    print(f"ターゲット: ID={window_id}, App={owner}, Title={title}")
    print("- 赤い抽出マスクを生で表示します（ノイズ処理なし）")
    if utils.ENABLE_TUNING:
        print("- [調整モード] HSV Controlsウィンドウでパラメータを調整できます")
    else:
        print("- [通常モード] 固定されたパラメータで動作します")
        print("  パラメータを調整したい場合は red_tracking_utils.py の ENABLE_TUNING を True にしてください")
    print("- 'q' または ESC で終了")
    print("=" * 50)

    while True:
        frame = capture_window(window_id)
        if frame is None:
            print("キャプチャ失敗（ウィンドウが閉じられた可能性）。リトライ中...")
            import time
            time.sleep(0.5)
            continue

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
            clss = results[0].boxes.cls.cpu().numpy().astype(int) # クラスID取得

            for box, obj_id, cls_id in zip(boxes, ids, clss):
                # obj_center = utils.get_object_center(box) # 不要になったのでコメントアウトまたは削除
                obj_name = model.names[cls_id] # クラス名取得

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
        cv2.rectangle(annotated_frame, (10, 10), (250, 100), (0, 0, 0), -1)
        cv2.putText(annotated_frame, f"Crossings: {tracker.get_total_crossings()}",
                   (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(annotated_frame, f"Red Frames: {len(red_frames)}",
                   (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
        # 現在のHSVパラメータを表示
        hsv_params = utils.hsv_params
        cv2.putText(annotated_frame, f"H:{hsv_params.h1_low}-{hsv_params.h1_high}/{hsv_params.h2_low}-{hsv_params.h2_high}",
                   (20, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # ウィンドウに表示
        if SHOW_TRACKER_WINDOW:
            cv2.imshow("Red Frame Crossing Tracker", annotated_frame)
        if SHOW_MASK_WINDOW:
            cv2.imshow("Red Mask", mask)

        # 終了判定
        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), 27):
            break

    # 最終統計を表示
    print("\n" + "=" * 50)
    print("最終統計")
    print("=" * 50)
    print(f"総通過回数: {tracker.get_total_crossings()}")
    if utils.ENABLE_TUNING:
        hsv_params = utils.hsv_params
        print("\n最終HSVパラメータ:")
        print(f"  H1: {hsv_params.h1_low} - {hsv_params.h1_high}")
        print(f"  H2: {hsv_params.h2_low} - {hsv_params.h2_high}")
        print(f"  S:  {hsv_params.s_low} - {hsv_params.s_high}")
        print(f"  V:  {hsv_params.v_low} - {hsv_params.v_high}")
    print("=" * 50)

    # Quartzはリソース解放不要
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
