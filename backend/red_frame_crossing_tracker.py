"""
赤い枠を通過する物体をリアルタイムで追跡するスクリプト（メイン）

機能:
- YOLOv11で物体を追跡（ID維持）
- 赤い枠（穴あき長方形）を検出（red_tracking_utilsを使用）
- 物体が赤い枠の開口部を通過したかを判定・記録
- トラックバーでHSVパラメータをリアルタイム調整可能
"""

import cv2
from ultralytics import YOLO
import red_tracking_utils as utils

def main():
    # YOLOv12のモデルをロード
    model = YOLO("yolo12n.pt")

    # Webカメラの起動
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("カメラを開けませんでした。VideoCapture(0) を変更してください。")

    # HSVトラックバーを作成（調整モード時のみ）
    if utils.ENABLE_TUNING:
        utils.create_trackbars()

    # 通過追跡器
    tracker = utils.CrossingTracker()

    frame_count = 0

    print("=" * 50)
    print("赤い枠通過トラッカー（モジュール版）")
    print("=" * 50)
    print("- 赤い抽出マスクを生で表示します（ノイズ処理なし）")
    if utils.ENABLE_TUNING:
        print("- [調整モード] HSV Controlsウィンドウでパラメータを調整できます")
    else:
        print("- [通常モード] 固定されたパラメータで動作します")
        print("  パラメータを調整したい場合は red_tracking_utils.py の ENABLE_TUNING を True にしてください")
    print("- 'q' または ESC で終了")
    print("=" * 50)

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

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
        cv2.imshow("Red Frame Crossing Tracker", annotated_frame)
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

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
