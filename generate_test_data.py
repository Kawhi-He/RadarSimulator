import random

random.seed(99)

timestamp_base = 45
timestamp_step = 100
frame_idx = 0
lines = []


def gen_frame(range_val, velocity, has_anomaly=False):
    global frame_idx
    ts = timestamp_base + frame_idx * timestamp_step + random.randint(-2, 2)
    power = round(-4065 - range_val * 1.0 + random.uniform(-1, 1), 1)
    angle_az = round(random.uniform(-0.2, 0.2), 1)
    lines.append("[HEAD]")
    lines.append(f"  TimeStamp={ts}")
    lines.append("  FrameID=0")
    lines.append("  AlarmType=0")
    lines.append("  RCW=0")
    lines.append("  BSD=0")
    lines.append("  LCA=0")
    lines.append("  YawRate=nan")
    lines.append("  CarSpeed=nan")
    lines.append("  EgoSpeed=nan")
    lines.append("  WaveT=0")
    lines.append("  Gear=0")
    lines.append("  PointNum=1")
    lines.append("  ObjectNum=0")
    lines.append("[Point]")
    lines.append(f"  0:Range={round(range_val, 2)} Velocity={velocity} AngleAZ={angle_az} AngleEL=0 Power={power}")
    lines.append("[Object]")
    lines.append("")
    frame_idx += 1


def gen_empty_frame():
    global frame_idx
    ts = timestamp_base + frame_idx * timestamp_step + random.randint(-2, 2)
    lines.append("[HEAD]")
    lines.append(f"  TimeStamp={ts}")
    lines.append("  FrameID=0")
    lines.append("  AlarmType=0")
    lines.append("  RCW=0")
    lines.append("  BSD=0")
    lines.append("  LCA=0")
    lines.append("  YawRate=nan")
    lines.append("  CarSpeed=nan")
    lines.append("  EgoSpeed=nan")
    lines.append("  WaveT=0")
    lines.append("  Gear=0")
    lines.append("  PointNum=0")
    lines.append("  ObjectNum=0")
    lines.append("[Point]")
    lines.append("[Object]")
    lines.append("")
    frame_idx += 1


def gen_loss_frames(count=3):
    for _ in range(count):
        gen_empty_frame()


# === Segment 1: 10m/s, moving away, step=1.0m, NORMAL ===
print("Segment 1: 10m/s, step=1.0m, normal (Range 2.0 -> 11.0)")
for r in [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0]:
    gen_frame(r, 10.0)

# Loss: 3 empty frames -> loss at 11.0m
gen_loss_frames(3)

# === Segment 2: 5m/s, moving away, step=0.5m, NORMAL ===
print("Segment 2: 5m/s, step=0.5m, normal (Range 12.0 -> 16.5)")
for r in [12.0, 12.5, 13.0, 13.5, 14.0, 14.5, 15.0, 15.5, 16.0, 16.5]:
    gen_frame(r, 5.0)

# Loss: 3 empty frames -> loss at 16.5m
gen_loss_frames(3)

# === Segment 3: 10m/s, moving away, step=1.0m, ANOMALY at frame 5 ===
# Expected: 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0
# Actual:   2.0, 3.0, 4.0, 5.0, 6.0, 8.5, 8.0, 9.0, 10.0, 11.0
# Anomaly: frame 5 Range=8.5 instead of expected 7.0, deviation=1.5m
print("Segment 3: 10m/s, step=1.0m, ANOMALY (frame 6: Range=8.5, expected=7.0, deviation=1.5m)")
anomaly3 = [2.0, 3.0, 4.0, 5.0, 6.0, 8.5, 8.0, 9.0, 10.0, 11.0]
for r in anomaly3:
    gen_frame(r, 10.0)

# Loss: 3 empty frames -> loss at 11.0m
gen_loss_frames(3)

# === Segment 4: 5m/s, moving away, step=0.5m, NORMAL ===
print("Segment 4: 5m/s, step=0.5m, normal (Range 2.0 -> 6.5)")
for r in [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5]:
    gen_frame(r, 5.0)

# Loss: 3 empty frames -> loss at 6.5m
gen_loss_frames(3)

# === Segment 5: 5m/s, moving away, step=0.5m, ANOMALY at frame 4 ===
# Expected: 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5
# Actual:   2.0, 2.5, 3.0, 5.2, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5
# Anomaly: frame 3 Range=5.2 instead of expected 3.5, deviation=1.7m
print("Segment 5: 5m/s, step=0.5m, ANOMALY (frame 4: Range=5.2, expected=3.5, deviation=1.7m)")
anomaly5 = [2.0, 2.5, 3.0, 5.2, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5]
for r in anomaly5:
    gen_frame(r, 5.0)

# Loss: 5 empty frames -> loss at 6.5m
gen_loss_frames(5)

if lines and lines[-1] == "":
    lines = lines[:-1]

with open(r"f:\Scripts\RadarSimulator\frame.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"\nGenerated {frame_idx} frames total")
print("Expected results:")
print("  Loss events: 5 (at 11.0m, 16.5m, 11.0m, 6.5m, 6.5m)")
print("  Velocity anomalies: 2")
print("    - Segment 3 frame 6: actual=8.5m, expected=7.0m, deviation=1.5m")
print("    - Segment 5 frame 4: actual=5.2m, expected=3.5m, deviation=1.7m")
