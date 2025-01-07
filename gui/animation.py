import os
import math
import shutil
import time

GRADIENT_CHARS = ['░', '▒', '▓', '█']

COLORS = [
    '\033[38;5;53m',  # Dark purple
    '\033[38;5;54m',  # Medium purple
    '\033[38;5;55m',  # Bright purple
    '\033[38;5;129m',  # Very bright purple
]

RESET_COLOR = '\033[0m'

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


def get_terminal_size():
    columns, rows = shutil.get_terminal_size()
    return columns, rows


def get_point_gradient(distance, target_radius, thickness=1.8):
    distance_from_line = abs(distance - target_radius)

    if distance_from_line > thickness:
        return -1

    gradient_index = int((thickness - distance_from_line) * len(GRADIENT_CHARS) / thickness)
    gradient_index = min(gradient_index, len(GRADIENT_CHARS) - 1)
    return gradient_index


def is_point_in_circle(x, y, center_x, center_y, radius, current_angle, arc_length):
    adjusted_x = x * (5 / 12)
    adjusted_center_x = center_x * (5 / 12)

    distance = math.sqrt((adjusted_x - adjusted_center_x) ** 2 + (y - center_y) ** 2)

    gradient_index = get_point_gradient(distance, radius, thickness=1.8)
    if gradient_index < 0:
        return None

    point_angle = math.degrees(math.atan2(y - center_y, adjusted_x - adjusted_center_x))
    point_angle = (point_angle + 360) % 360

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


def overlay_ascii_art(screen, center_x, center_y, ascii_art):
    ascii_height = len(ascii_art)
    ascii_width = len(ascii_art[0])

    start_y = center_y - ascii_height // 2
    start_x = center_x - ascii_width // 2

    for i, line in enumerate(ascii_art):
        for j, char in enumerate(line):
            if char != ' ':
                screen_y = start_y + i
                screen_x = start_x + j

                if 0 <= screen_y < len(screen) and 0 <= screen_x < len(screen[0]):
                    screen[screen_y][screen_x] = f"{COLORS[-1]}{char}{RESET_COLOR}"


def animation():
    width, height = get_terminal_size()

    center_x = width // 2
    center_y = height // 2
    radius = min(height, height) // 4 * 1.3

    try:
        angle = 0
        arc_length = 180
        direction = 1
        while True:
            screen = [[' ' for _ in range(width)] for _ in range(height)]

            for y in range(height):
                for x in range(width):
                    gradient_index = is_point_in_circle(x, y, center_x, center_y, radius, angle, arc_length)
                    if gradient_index is not None:
                        char = GRADIENT_CHARS[gradient_index]
                        color = COLORS[gradient_index]
                        screen[y][x] = f"{color}{char}{RESET_COLOR}"

            overlay_ascii_art(screen, center_x, center_y, ASCII_ART)

            print('\033[2J\033[?25l', end='')
            print('\033[H' + '\n'.join(''.join(row) for row in screen), end='', flush=True)

            angle = (angle - 25) % 360

            arc_length += direction * 8

            if arc_length >= 240 or arc_length <= 45:
                direction *= -1

            time.sleep(0.04)

    except KeyboardInterrupt:
        print('\033[?25h', end='')


if __name__ == "__main__":
    animation()
