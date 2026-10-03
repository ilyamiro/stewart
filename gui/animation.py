import os
import math
import shutil
import time
import random

# Enhanced visual elements
GRADIENT_CHARS = ['░', '▒', '▓', '█', '█']  # Added extra █ for more solid sections
COLORS = [
    '\033[38;5;53m',  # Dark purple
    '\033[38;5;54m',  # Medium purple
    '\033[38;5;55m',  # Bright purple
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


def spawn_particles(particles, center_x, center_y, angle, count=3):
    # Spawn new particles at the ends of the arc
    for _ in range(count):
        # Convert angles to radians for particle spawning
        for spawn_angle in [angle, (angle + 180) % 360]:
            rad_angle = math.radians(spawn_angle)
            radius = min(center_y, center_x) // 3 * 1.3

            # Position particles at the arc edges
            x = center_x + math.cos(rad_angle) * radius * (12 / 5)  # Adjust for aspect ratio
            y = center_y + math.sin(rad_angle) * radius

            # Add some randomness to velocity
            speed = random.uniform(0.5, 1.5)
            vx = math.cos(rad_angle) * speed + random.uniform(-0.3, 0.3)
            vy = math.sin(rad_angle) * speed + random.uniform(-0.3, 0.3)

            particles.append(Particle(x, y, vx, vy, random.randint(20, 30)))

    return particles


def animation():
    width, height = get_terminal_size()
    center_x = width // 2
    center_y = height // 2
    radius = min(height, width) // 4 * 1.3

    particles = []
    pulse = 0

    try:
        angle = 0
        arc_length = 180
        direction = 1
        frame_count = 0

        while True:
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
                particles = spawn_particles(particles, center_x, center_y, angle)

            particles = update_particles(particles, center_x, center_y, width, height)
            render_particles(screen, particles)

            # Draw the ASCII art with pulsing effect
            pulse += 0.1
            overlay_ascii_art(screen, center_x, center_y, ASCII_ART, pulse)

            # Clear screen and hide cursor
            print('\033[2J\033[?25l', end='')

            # Render the frame
            print('\033[H' + '\n'.join(''.join(row) for row in screen), end='', flush=True)

            # Update animation parameters
            angle = (angle - 5) % 360  # Slowed down rotation speed for smoother effect
            arc_length += direction * 3  # Slower arc length changes

            # Change direction when needed
            if arc_length >= 240 or arc_length <= 45:
                direction *= -1

            # Add a slight variation to the timing for more organic feel
            sleep_time = 0.033 + random.uniform(-0.005, 0.005)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        pass
