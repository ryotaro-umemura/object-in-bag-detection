"""
赤い枠の検出と追跡のためのユーティリティモジュール
"""

import cv2
import numpy as np
from collections import defaultdict

# ---- 設定 ----
ENABLE_TUNING = False       # True: パラメータ調整モード（トラックバー表示）, False: 通常モード

# ---- 赤い枠検出パラメータ ----
MIN_OUTER_AREA = 1000      # 赤い外枠の最小面積
MIN_INNER_AREA = 300       # 穴（内側）の最小面積
HOLE_RATIO_MIN = 0.10      # inner/outer の下限
HOLE_RATIO_MAX = 0.90      # inner/outer の上限

# ---- 通過判定パラメータ ----
CROSSING_THRESHOLD = 30    # 中心からこの距離以内で通過とみなす（ピクセル）

# ---- HSVパラメータのデフォルト値（調整済み） ----
DEFAULT_H1_LOW = 0
DEFAULT_H1_HIGH = 9
DEFAULT_H2_LOW = 150
DEFAULT_H2_HIGH = 180
DEFAULT_S_LOW = 160
DEFAULT_S_HIGH = 255
DEFAULT_V_LOW = 193
DEFAULT_V_HIGH = 255


class HSVParams:
    """HSVパラメータを管理するクラス"""
    def __init__(self):
        self.h1_low = DEFAULT_H1_LOW
        self.h1_high = DEFAULT_H1_HIGH
        self.h2_low = DEFAULT_H2_LOW
        self.h2_high = DEFAULT_H2_HIGH
        self.s_low = DEFAULT_S_LOW
        self.s_high = DEFAULT_S_HIGH
        self.v_low = DEFAULT_V_LOW
        self.v_high = DEFAULT_V_HIGH


# グローバルなHSVパラメータ
hsv_params = HSVParams()


def nothing(x):
    """トラックバーのコールバック（何もしない）"""
    pass


def create_trackbars():
    """HSVパラメータ調整用のトラックバーを作成"""
    cv2.namedWindow("HSV Controls", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("HSV Controls", 400, 350)

    # 赤色範囲1 (H=0付近)
    cv2.createTrackbar("H1 Low", "HSV Controls", DEFAULT_H1_LOW, 180, nothing)
    cv2.createTrackbar("H1 High", "HSV Controls", DEFAULT_H1_HIGH, 180, nothing)

    # 赤色範囲2 (H=180付近)
    cv2.createTrackbar("H2 Low", "HSV Controls", DEFAULT_H2_LOW, 180, nothing)
    cv2.createTrackbar("H2 High", "HSV Controls", DEFAULT_H2_HIGH, 180, nothing)

    # 彩度 (S)
    cv2.createTrackbar("S Low", "HSV Controls", DEFAULT_S_LOW, 255, nothing)
    cv2.createTrackbar("S High", "HSV Controls", DEFAULT_S_HIGH, 255, nothing)

    # 明度 (V)
    cv2.createTrackbar("V Low", "HSV Controls", DEFAULT_V_LOW, 255, nothing)
    cv2.createTrackbar("V High", "HSV Controls", DEFAULT_V_HIGH, 255, nothing)


def update_hsv_params():
    """トラックバーからHSVパラメータを読み取って更新（Low > Highなら入れ替え）"""
    h1_low = cv2.getTrackbarPos("H1 Low", "HSV Controls")
    h1_high = cv2.getTrackbarPos("H1 High", "HSV Controls")
    h2_low = cv2.getTrackbarPos("H2 Low", "HSV Controls")
    h2_high = cv2.getTrackbarPos("H2 High", "HSV Controls")
    s_low = cv2.getTrackbarPos("S Low", "HSV Controls")
    s_high = cv2.getTrackbarPos("S High", "HSV Controls")
    v_low = cv2.getTrackbarPos("V Low", "HSV Controls")
    v_high = cv2.getTrackbarPos("V High", "HSV Controls")

    # Low > High の場合は入れ替える
    hsv_params.h1_low, hsv_params.h1_high = min(h1_low, h1_high), max(h1_low, h1_high)
    hsv_params.h2_low, hsv_params.h2_high = min(h2_low, h2_high), max(h2_low, h2_high)
    hsv_params.s_low, hsv_params.s_high = min(s_low, s_high), max(s_low, s_high)
    hsv_params.v_low, hsv_params.v_high = min(v_low, v_high), max(v_low, v_high)


def red_mask_hsv(bgr):
    """HSV空間で赤色マスクを生成（シンプル版）"""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    # 赤は H=0 近傍と 180 近傍に分離
    lower1 = np.array([hsv_params.h1_low, hsv_params.s_low, hsv_params.v_low])
    upper1 = np.array([hsv_params.h1_high, hsv_params.s_high, hsv_params.v_high])
    lower2 = np.array([hsv_params.h2_low, hsv_params.s_low, hsv_params.v_low])
    upper2 = np.array([hsv_params.h2_high, hsv_params.s_high, hsv_params.v_high])

    m1 = cv2.inRange(hsv, lower1, upper1)
    m2 = cv2.inRange(hsv, lower2, upper2)
    mask = cv2.bitwise_or(m1, m2)

    # モルフォロジー処理（ごく軽くのみ適用、あるいは無くてもよいがノイズ除去のため最小限）
    # 完全にマスクが見えなくなるのを防ぐため、まずは処理なし、あるいはOpenでノイズ除去程度
    # ここではごま塩ノイズ除去のためにMedianBlurを使うのも手だが、morphologyEx(OPEN)が無難
    k = np.ones((3, 3), np.uint8)
    # mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)

    # マスクが見えないときはこれさえも邪魔になることがあるので、一旦生のマスクを返す
    # 必要に応じて有効化してください

    return mask


def contour_center(cnt):
    """輪郭の重心を計算"""
    M = cv2.moments(cnt)
    if M["m00"] == 0:
        return None
    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])
    return (cx, cy)


def detect_red_frames(mask):
    """
    赤い枠（穴あき、または途切れた枠）を検出

    Returns:
        list of dict: 検出された枠の情報
            - outer_bbox: 外枠のバウンディングボックス (x, y, w, h)
            - center: 通過判定用の中心座標（穴があれば穴の重心、なければBBox中心）
            - inner_contour: 内側輪郭（なければNone）
            - outer_contour: 外側輪郭
    """
    # 輪郭検出
    cnts, hier = cv2.findContours(mask.copy(), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return []

    hier = hier[0]
    detections = []

    for i, c_outer in enumerate(cnts):
        # 面積チェック（ノイズ除去）
        outer_area = cv2.contourArea(c_outer)
        if outer_area < MIN_OUTER_AREA:
            continue

        x, y, w, h = cv2.boundingRect(c_outer)
        if w == 0 or h == 0:
            continue

        # 形状チェック（極端に細長いものは除外）
        ar = w / h
        if ar < 0.2 or ar > 5.0:
            continue

        child_idx = hier[i][2]

        # --- ケース1: 穴（内側輪郭）がある場合 ---
        if child_idx != -1:
            c_inner = cnts[child_idx]
            inner_area = cv2.contourArea(c_inner)

            # 穴がそれなりの大きさなら「完全な枠」として扱う
            if inner_area >= MIN_INNER_AREA:
                center = contour_center(c_inner)
                if center is not None:
                    detections.append({
                        "outer_bbox": (x, y, w, h),
                        "center": center,
                        "inner_contour": c_inner,
                        "outer_contour": c_outer,
                        "type": "hole"
                    })
                    continue

        # --- ケース2: 穴がない、または穴が小さい場合（途切れた枠など） ---
        # バウンディングボックスの中心を通過地点とする
        center_x = int(x + w / 2)
        center_y = int(y + h / 2)

        detections.append({
            "outer_bbox": (x, y, w, h),
            "center": (center_x, center_y),
            "inner_contour": None, # 穴なし
            "outer_contour": c_outer,
            "type": "bbox"
        })

    return detections


def get_object_center(box):
    """YOLOのバウンディングボックスから中心座標を計算"""
    x1, y1, x2, y2 = box
    return (int((x1 + x2) / 2), int((y1 + y2) / 2))


def is_point_near_center(point, center, threshold):
    """点が中心から一定距離以内かを判定"""
    dx = point[0] - center[0]
    dy = point[1] - center[1]
    distance = np.sqrt(dx**2 + dy**2)
    return distance < threshold


def is_point_in_bbox(point, bbox):
    """点がバウンディングボックス内にあるかを判定"""
    x, y, w, h = bbox
    px, py = point
    # 少しマージンを持たせて判定（内側 80% くらいに入っていればOKとする）
    margin_x = w * 0.1
    margin_y = h * 0.1
    return (x + margin_x <= px <= x + w - margin_x) and \
           (y + margin_y <= py <= y + h - margin_y)


def get_box_area(box):
    """バウンディングボックスの面積を計算"""
    x, y, w, h = box
    return w * h


class CrossingTracker:
    """物体の赤枠通過を追跡するクラス"""

    def __init__(self):
        self.crossing_counts = defaultdict(int)
        self.was_inside = defaultdict(bool)
        self.total_crossings = 0

    def update(self, object_id, object_box_xyxy, red_frames):
        """
        物体の位置を更新し、通過判定を行う

        Args:
            object_id: 物体のトラッキングID
            object_box_xyxy: 物体のBBox [x1, y1, x2, y2]
            red_frames: 検出された赤い枠のリスト
        """
        # 物体の情報を計算
        obj_x1, obj_y1, obj_x2, obj_y2 = object_box_xyxy
        obj_center = (int((obj_x1 + obj_x2) / 2), int((obj_y1 + obj_y2) / 2))

        obj_w = obj_x2 - obj_x1
        obj_h = obj_y2 - obj_y1
        obj_area = obj_w * obj_h

        is_inside_now = False

        for frame_info in red_frames:
            # 赤い枠の情報
            frame_bbox = frame_info["outer_bbox"] # (x, y, w, h)
            frame_w, frame_h = frame_bbox[2], frame_bbox[3]
            frame_area = frame_w * frame_h

            # 条件1: 物体のサイズが赤い枠より小さいこと
            if obj_area >= frame_area:
                continue

            # 条件2: 物体の重心が赤い枠のバウンディングボックス内にあること
            if is_point_in_bbox(obj_center, frame_bbox):
                is_inside_now = True
                break

        # 前フレームで外側、今フレームで内側 → 通過とみなす
        crossed = False
        if is_inside_now and not self.was_inside[object_id]:
            self.crossing_counts[object_id] += 1
            self.total_crossings += 1
            crossed = True

        self.was_inside[object_id] = is_inside_now
        return crossed

    def get_total_crossings(self):
        return self.total_crossings
