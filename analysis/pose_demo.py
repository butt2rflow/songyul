"""Run MediaPipe Pose on a face-on golf swing and plot the resulting curves.

Shoulder and hip turn are unsigned 2D proxies based on how much the
projected joint-to-joint widths shrink relative to the address position.
Head sway is the nose's horizontal displacement in head widths.

Adapted from the sensor-glove project's src/pose_demo.py.
"""

import argparse
from pathlib import Path

import cv2
import matplotlib
import mediapipe as mp
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

EDGES = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23),
    (12, 24), (23, 24), (23, 25), (25, 27), (24, 26), (26, 28),
    (15, 17), (15, 19), (16, 18), (16, 20), (27, 31), (28, 32),
]

LABELS = {
    "en": {
        "shoulder": "Shoulder turn",
        "hip": "Hip turn",
        "sway": "Head sway",
        "sway_axis": "Head sway (head widths)",
        "top": "Top of backswing",
        "fast": "Peak hand speed (near impact)",
        "time": "Time (s)",
        "turn": "Estimated turn (°)",
        "title": "Swing curves from MediaPipe landmarks (AI-generated video, face-on)",
    },
    "ko": {
        "shoulder": "어깨 회전",
        "hip": "골반 회전",
        "sway": "머리 좌우 이동",
        "sway_axis": "머리 이동 (머리 폭 단위)",
        "top": "탑",
        "fast": "손이 가장 빠름 (임팩트 근처)",
        "time": "시간 (s)",
        "turn": "회전 (°, 대략)",
        "title": "MediaPipe 점으로 계산한 스윙 곡선 (AI 영상, 정면 카메라)",
    },
}


def track_pose(video, out_dir):
    cap = cv2.VideoCapture(str(video))
    writer = None
    points, visibility, frames = [], [], []
    try:
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {video}")
        fps = cap.get(cv2.CAP_PROP_FPS) or 24
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        writer = cv2.VideoWriter(
            str(out_dir / "pose_raw.mp4"), cv2.VideoWriter_fourcc(*"mp4v"),
            fps, (width, height),
        )
        if not writer.isOpened():
            raise ValueError("Cannot open the annotated video for writing.")

        with mp.solutions.pose.Pose(model_complexity=1) as detector:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = detector.process(rgb)
                if result.pose_landmarks:
                    landmarks = result.pose_landmarks.landmark
                    xy = np.array([(q.x * width, q.y * height) for q in landmarks])
                    scores = np.array([q.visibility for q in landmarks])
                    pixels = xy.astype(int)
                    for a, b in EDGES:
                        if scores[a] > 0.4 and scores[b] > 0.4:
                            cv2.line(frame, tuple(pixels[a]), tuple(pixels[b]),
                                     (255, 230, 80), 3, cv2.LINE_AA)
                    for joint, pixel in enumerate(pixels):
                        if scores[joint] > 0.4:
                            color = (40, 40, 230) if joint in (15, 16) else (255, 255, 255)
                            cv2.circle(frame, tuple(pixel), 4, color, -1, cv2.LINE_AA)
                else:
                    xy = np.full((33, 2), np.nan)
                    scores = np.zeros(33)
                points.append(xy)
                visibility.append(scores)
                writer.write(frame)
                frames.append(frame)
    finally:
        cap.release()
        if writer is not None:
            writer.release()

    if not points or not np.isfinite(points).any():
        raise ValueError("No pose landmarks found in the video.")
    return np.array(points), np.array(visibility), frames, fps


def estimated_turn(points, left, right, address_count):
    widths = np.linalg.norm(points[:, left] - points[:, right], axis=1)
    return np.degrees(np.arccos(np.clip(widths / np.nanmedian(widths[:address_count]), 0, 1)))


def plot_curves(path, lang, time, shoulder, hip, sway, top, fast):
    labels = LABELS[lang]
    fonts = ["Noto Sans CJK KR", "DejaVu Sans"] if lang == "ko" else ["DejaVu Sans"]
    with plt.rc_context({"font.family": fonts, "font.size": 11, "figure.facecolor": "#fbfaf7"}):
        fig, ax = plt.subplots(figsize=(11, 4.5))
        shoulder_line, = ax.plot(time, shoulder, color="#1f6fb2", lw=2.2, label=labels["shoulder"])
        hip_line, = ax.plot(time, hip, color="#2e7d4f", lw=2.2, label=labels["hip"])
        ax2 = ax.twinx()
        sway_line, = ax2.plot(time, sway, color="#c0392b", lw=1.6, ls="--", label=labels["sway"])
        ax2.set_ylabel(labels["sway_axis"], color="#c0392b")
        for frame, key, offset, alignment in ((top, "top", -4, "right"), (fast, "fast", 4, "left")):
            ax.axvline(time[frame], color="#555", lw=1, ls=":")
            ax.annotate(labels[key], (time[frame], 1), xycoords=ax.get_xaxis_transform(),
                        xytext=(offset, 6), textcoords="offset points",
                        ha=alignment, va="bottom", fontsize=9, color="#555")
        ax.set(xlabel=labels["time"], ylabel=labels["turn"])
        ax.legend(handles=[shoulder_line, hip_line, sway_line],
                  loc="upper center", bbox_to_anchor=(0.5, -0.17), ncols=3, frameon=False)
        ax.set_title(labels["title"], loc="left", weight="bold", pad=25)
        fig.savefig(path, dpi=120, bbox_inches="tight")
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--lang", choices=("en", "ko"), default="en", help="plot language (default: en)")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    points, visibility, frames, fps = track_pose(args.video, args.out_dir)
    time = np.arange(len(points)) / fps
    address_count = max(1, int(0.5 * fps))
    shoulder = estimated_turn(points, 11, 12, address_count)
    hip = estimated_turn(points, 23, 24, address_count)
    address = points[:address_count]
    head_width = np.nanmedian(np.linalg.norm(address[:, 7] - address[:, 8], axis=1))
    sway = (points[:, 0, 0] - np.nanmedian(address[:, 0, 0])) / head_width
    if not all(np.isfinite(series).any() for series in (shoulder, hip, sway)):
        raise ValueError("Cannot estimate the turning or sway curves from the address frames.")

    hands = (points[:, 15] + points[:, 16]) / 2
    speed = np.r_[0, np.linalg.norm(np.diff(hands, axis=0), axis=1)]
    fast = int(np.nanargmax(speed))
    # Peak shoulder turn before peak hand speed avoids marking the finish as the top.
    top = int(np.nanargmax(shoulder[:fast])) if fast > 2 and np.isfinite(shoulder[:fast]).any() else 0
    np.savez(args.out_dir / "pose.npz", t=time, pts=points, vis=visibility,
             shoulder_turn=shoulder, hip_turn=hip, head_sway=sway)
    plot_curves(args.out_dir / "pose-curves.png", args.lang, time, shoulder, hip, sway, top, fast)

    height, width = frames[0].shape[:2]
    indices = np.linspace(0, len(frames) - 1, 6).astype(int)
    indices[3] = top
    crops = [cv2.resize(frames[k][:, width // 4:3 * width // 4],
                        (300, int(600 * height / width))) for k in sorted(set(indices))]
    cv2.imwrite(str(args.out_dir / "pose-frames.png"), np.concatenate(crops, axis=1))
    detected = np.isfinite(points[:, 0, 0]).sum()
    print(f"Pose detected in {detected}/{len(points)} frames at {fps:g} fps.")
    print(f"Mean visibility: wrists {visibility[:, 15:17].mean():.2f}, "
          f"shoulders {visibility[:, 11:13].mean():.2f}, hips {visibility[:, 23:25].mean():.2f}.")
    print(f"Top of backswing at {time[top]:.2f} s, peak hand speed at {time[fast]:.2f} s.")
    print(f"At the top: shoulder turn {shoulder[top]:.0f}°, hip turn {hip[top]:.0f}°, "
          f"difference {shoulder[top] - hip[top]:.0f}°. "
          f"Peak head sway through peak hand speed: {np.nanmax(np.abs(sway[:fast + 1])):.2f} head widths.")


if __name__ == "__main__":
    main()
