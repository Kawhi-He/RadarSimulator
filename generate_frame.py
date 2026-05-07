import random

random.seed(42)

start_range = 2.0
range_step = 1.0
max_detect_range = 28.0
loss_frames = 5
timestamp_base = 45
timestamp_step = 100

lines = []
frame_idx = 0
current_range = start_range

while current_range < max_detect_range:
    ts = timestamp_base + frame_idx * timestamp_step + random.randint(-5, 5)
    power = round(-4065 - (current_range - start_range) * (30.0 / (max_detect_range - start_range)) + random.uniform(-2, 2), 1)
    velocity = round(10.0 + random.uniform(-0.5, 0.5), 1)
    angle_az = round(random.uniform(-0.3, 0.3), 1)

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
    lines.append(f"  0:Range={round(current_range, 2)} Velocity={velocity} AngleAZ={angle_az} AngleEL=0 Power={power}")
    lines.append("[Object]")
    lines.append("")

    current_range += range_step
    frame_idx += 1

for i in range(loss_frames):
    ts = timestamp_base + frame_idx * timestamp_step + random.randint(-5, 5)
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
    if i < loss_frames - 1:
        lines.append("")
    frame_idx += 1

with open(r"f:\Scripts\RadarSimulator\frame.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"Generated {frame_idx} frames")
print(f"  - Frames with point: {frame_idx - loss_frames}")
print(f"  - Frames without point (loss): {loss_frames}")
print(f"  - Range: {start_range}m -> {max_detect_range - range_step}m (last detected)")
print(f"  - At {max_detect_range}m, point lost (3+ consecutive frames with no data)")
