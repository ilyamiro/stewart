import os
import math
import shutil
import time
import random
import threading
import textwrap
import re

# Enhanced visual elements
GRADIENT_CHARS = ['░', '▒', '▓', '█', '█']  # Added extra █ for more solid sections
COLORS = [
    '\033[38;5;53m',   # Dark purple
    '\033[38;5;54m',   # Medium purple
    '\033[38;5;55m',   # Bright purple
    '\033[38;5;129m',  # Very bright purple
    '\033[38;5;183m',  # Light purple/pink
]

# BG_COLOR = '\033[48;2;0;0;0m'
RESET_COLOR = '\033[0m'

# Enhanced ASCII art with more detail
ASCII_ART = [
    "  █████████ ",
    " ███░░░░░███",
    "░███    ░░░ ",
    "░░█████████ ",
    " ░░░░░░░░███",
    " ███    ░███",
    "░░█████████ ",
    " ░░░░░░░░░  ",
]

ANSI_REGEX = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')

# Thread-safe conversation state
_state_lock = threading.Lock()
_conversation_state = {
    "user_text": "",
    "assistant_text": "",
    "user_timestamp": 0.0,
    "assistant_timestamp": 0.0,
}


def set_user_text(text: str):
    """Update the latest text spoken by the user."""
    if not text:
        return
    with _state_lock:
        _conversation_state["user_text"] = text.strip()
        _conversation_state["user_timestamp"] = time.time()


def set_assistant_text(text: str):
    """Update the latest response spoken by the voice assistant."""
    if not text:
        return
    with _state_lock:
        _conversation_state["assistant_text"] = text.strip()
        _conversation_state["assistant_timestamp"] = time.time()


def get_conversation_state():
    """Retrieve a snapshot of the current conversation state."""
    with _state_lock:
        return dict(_conversation_state)


def reset_conversation():
    """Reset the conversation state."""
    with _state_lock:
        _conversation_state["user_text"] = ""
        _conversation_state["assistant_text"] = ""
        _conversation_state["user_timestamp"] = 0.0
        _conversation_state["assistant_timestamp"] = 0.0


def strip_ansi(text: str) -> str:
    """Return text stripped of ANSI escape sequences."""
    return ANSI_REGEX.sub('', text)


def pad_row(content: str, width: int, left_margin: int) -> str:
    """Pad a formatted string to exactly width visible characters."""
    vis_len = len(strip_ansi(content))
    left_pad = ' ' * left_margin
    right_pad = ' ' * max(0, width - vis_len - left_margin)
    return left_pad + content + right_pad


# Particles for additional visual effects
class Particle:
    def __init__(self, x, y, vx, vy, life):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life
        self.max_life = life


def get_terminal_size():
    columns, rows = shutil.get_terminal_size()
    return columns, rows


def get_point_gradient(distance, target_radius, thickness=2.0):
    # Increased thickness for more visible circle
    distance_from_line = abs(distance - target_radius)
    if distance_from_line > thickness:
        return -1
    gradient_index = int((thickness - distance_from_line) * len(GRADIENT_CHARS) / thickness)
    gradient_index = min(gradient_index, len(GRADIENT_CHARS) - 1)
    return gradient_index


def is_point_in_circle(x, y, center_x, center_y, radius, current_angle, arc_length):
    # Adjust for terminal character aspect ratio
    adjusted_x = x * (5 / 12)
    adjusted_center_x = center_x * (5 / 12)

    # Calculate distance from center
    distance = math.sqrt((adjusted_x - adjusted_center_x) ** 2 + (y - center_y) ** 2)
    gradient_index = get_point_gradient(distance, radius, thickness=2.0)

    if gradient_index < 0:
        return None

    # Calculate angle of point
    point_angle = math.degrees(math.atan2(y - center_y, adjusted_x - adjusted_center_x))
    point_angle = (point_angle + 360) % 360

    if arc_length >= 360:
        return gradient_index

    # Check if point is in visible arc
    start_angle = current_angle
    end_angle = (start_angle + arc_length) % 360

    is_visible = False
    if start_angle <= end_angle:
        is_visible = start_angle <= point_angle <= end_angle
    else:
        is_visible = point_angle >= start_angle or point_angle <= end_angle

    if is_visible:
        return gradient_index
    return None


def overlay_ascii_art(screen, center_x, center_y, ascii_art, pulse):
    ascii_height = len(ascii_art)
    ascii_width = len(ascii_art[0])
    start_y = center_y - ascii_height // 2
    start_x = center_x - ascii_width // 2

    # Add pulsing effect to the text
    intensity = abs(math.sin(pulse)) * 0.7 + 0.3  # Range from 0.3 to 1.0
    color_index = int(intensity * (len(COLORS) - 1))

    for i, line in enumerate(ascii_art):
        for j, char in enumerate(line):
            if char != ' ':
                screen_y = start_y + i
                screen_x = start_x + j
                if 0 <= screen_y < len(screen) and 0 <= screen_x < len(screen[0]):
                    # Special highlight for the edges
                    if char == '█':
                        screen[screen_y][screen_x] = f"{COLORS[-1]}{char}{RESET_COLOR}"
                    else:
                        screen[screen_y][screen_x] = f"{COLORS[color_index]}{char}{RESET_COLOR}"


def update_particles(particles, center_x, center_y, width, height):
    # Update particle positions and remove dead ones
    updated_particles = []
    for p in particles:
        p.x += p.vx
        p.y += p.vy
        p.life -= 1

        # Apply gravity towards center
        dx = center_x - p.x
        dy = center_y - p.y
        dist = max(1, math.sqrt(dx * dx + dy * dy))
        p.vx += dx / dist * 0.05
        p.vy += dy / dist * 0.05

        # Add friction to slow down particles
        p.vx *= 0.98
        p.vy *= 0.98

        if p.life > 0 and 0 <= p.x < width and 0 <= p.y < height:
            updated_particles.append(p)

    return updated_particles


def render_particles(screen, particles):
    # Render particles with fading effect
    for p in particles:
        x, y = int(p.x), int(p.y)
        if 0 <= y < len(screen) and 0 <= x < len(screen[0]):
            fade = p.life / p.max_life
            color_idx = min(len(COLORS) - 1, int(fade * (len(COLORS) - 1)))
            char_idx = min(len(GRADIENT_CHARS) - 2, int(fade * (len(GRADIENT_CHARS) - 1)))
            screen[y][x] = f"{COLORS[color_idx]}{GRADIENT_CHARS[char_idx]}{RESET_COLOR}"


def spawn_particles(particles, center_x, center_y, angle, radius=None, count=3):
    # Spawn new particles at the ends of the arc
    if radius is None:
        radius = min(center_y, center_x) // 3 * 1.3

    for _ in range(count):
        # Convert angles to radians for particle spawning
        for spawn_angle in [angle, (angle + 180) % 360]:
            rad_angle = math.radians(spawn_angle)

            # Position particles at the arc edges
            x = center_x + math.cos(rad_angle) * radius * (12 / 5)  # Adjust for aspect ratio
            y = center_y + math.sin(rad_angle) * radius

            # Add some randomness to velocity
            speed = random.uniform(0.5, 1.5)
            vx = math.cos(rad_angle) * speed + random.uniform(-0.3, 0.3)
            vy = math.sin(rad_angle) * speed + random.uniform(-0.3, 0.3)

            particles.append(Particle(x, y, vx, vy, random.randint(20, 30)))

    return particles


def build_conversation_lines(width: int, height: int):
    """Format the user speech and assistant response for rendering at the bottom."""
    state = get_conversation_state()
    user_text = state["user_text"]
    asst_text = state["assistant_text"]
    u_time = state["user_timestamp"]
    a_time = state["assistant_timestamp"]

    max_text_width = max(20, min(width - 8, 70))
    margin = max(2, (width - max_text_width) // 2)

    conv_lines = []
    if height >= 22:
        conv_lines.append(f"\033[38;5;54m{'─' * max_text_width}\033[0m")

    # User speech section
    user_label = "\033[1;38;5;183mYou:\033[0m "
    user_prefix_len = 5
    if user_text:
        wrapped_user = textwrap.wrap(user_text, width=max(10, max_text_width - user_prefix_len))
        for idx, w in enumerate(wrapped_user[:2]):
            if idx == 0:
                conv_lines.append(f"{user_label}\033[38;5;255m{w}\033[0m")
            else:
                conv_lines.append(f"{' ' * user_prefix_len}\033[38;5;255m{w}\033[0m")
    else:
        conv_lines.append(f"{user_label}\033[38;5;243m(say \"Stewart\" to speak)\033[0m")

    if height >= 24:
        conv_lines.append("")

    # Voice assistant response section
    asst_label = "\033[1;38;5;129mStewart:\033[0m "
    asst_prefix_len = 9
    max_asst_lines = 4 if height >= 30 else 3
    if u_time > a_time and user_text:
        conv_lines.append(f"{asst_label}\033[38;5;243mThinking...\033[0m")
    elif asst_text:
        wrapped_asst = textwrap.wrap(asst_text, width=max(10, max_text_width - asst_prefix_len))
        for idx, w in enumerate(wrapped_asst[:max_asst_lines]):
            if idx == 0:
                conv_lines.append(f"{asst_label}\033[38;5;252m{w}\033[0m")
            else:
                conv_lines.append(f"{' ' * asst_prefix_len}\033[38;5;252m{w}\033[0m")
    else:
        conv_lines.append(f"{asst_label}\033[38;5;243mStanding by...\033[0m")

    return conv_lines, margin


def animation():
    particles = []
    pulse = 0

    try:
        angle = 0
        arc_length = 180
        direction = 1
        frame_count = 0

        while True:
            width, height = get_terminal_size()
            width = max(24, width)
            height = max(12, height)

            # Build conversation overlay lines for bottom display
            conv_lines, margin = build_conversation_lines(width, height)
            num_text_lines = len(conv_lines)
            start_text_y = height - num_text_lines - 1

            available_height = max(10, start_text_y)
            center_x = width // 2
            center_y = max(5, available_height // 2)
            radius = max(5.8, min(available_height - 3, width // 2) / 3.0 * 1.15)

            # Create a new screen with background color
            screen = [[f" " for _ in range(width)] for _ in range(height)]

            # Draw the arc
            for y in range(height):
                for x in range(width):
                    gradient_index = is_point_in_circle(x, y, center_x, center_y, radius, angle, arc_length)
                    if gradient_index is not None:
                        char = GRADIENT_CHARS[gradient_index]
                        color = COLORS[gradient_index]
                        screen[y][x] = f"{color}{char}{RESET_COLOR}"

            # Update and render particles
            frame_count += 1
            if frame_count % 3 == 0:  # Spawn particles every few frames
                particles = spawn_particles(particles, center_x, center_y, angle, radius)

            particles = update_particles(particles, center_x, center_y, width, height)
            render_particles(screen, particles)

            # Draw the ASCII art with pulsing effect
            pulse += 0.1
            overlay_ascii_art(screen, center_x, center_y, ASCII_ART, pulse)

            # Overlay conversation text at the bottom
            for i, line in enumerate(conv_lines):
                target_y = start_text_y + i
                if 0 <= target_y < height:
                    screen[target_y] = [pad_row(line, width, margin)]

            # Clear screen and hide cursor
            print('\033[2J\033[?25l', end='')

            # Render the frame
            print('\033[H' + '\n'.join(''.join(row) for row in screen), end='', flush=True)

            # Update animation parameters
            angle = (angle - 5) % 360  # Rotation speed for smooth effect
            arc_length += direction * 3  # Arc length changes

            # Change direction when needed
            if arc_length >= 240 or arc_length <= 45:
                direction *= -1

            # Organic timing variation
            sleep_time = 0.033 + random.uniform(-0.005, 0.005)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        pass
    finally:
        # Restore cursor visibility and reset color
        print('\033[?25h\033[0m', end='', flush=True)


if __name__ == "__main__":
    animation()
