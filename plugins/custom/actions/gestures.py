import time
import cv2
import mediapipe as mp
import math
from api import app
import subprocess

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(min_detection_confidence=0.7, min_tracking_confidence=0.7)

SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

smoothing_factor = 0.1

REACH_FACTOR = 1.5


def calculate_distance(point1, point2):
    return math.sqrt((point1[0] - point2[0]) ** 2 + (point1[1] - point2[1]) ** 2)


def move_cursor(index_tip, previous_position):
    cursor_x = int(index_tip[0] * SCREEN_WIDTH * REACH_FACTOR)
    cursor_y = int(index_tip[1] * SCREEN_HEIGHT * REACH_FACTOR)

    cursor_x = max(0, min(cursor_x, SCREEN_WIDTH - 1))
    cursor_y = max(0, min(cursor_y, SCREEN_HEIGHT - 1))

    smooth_x = previous_position[0] + (cursor_x - previous_position[0]) * smoothing_factor
    smooth_y = previous_position[1] + (cursor_y - previous_position[1]) * smoothing_factor

    previous_position[0] = smooth_x
    previous_position[1] = smooth_y

    app.mouse.position = (smooth_x, smooth_y)


def detect_pinch(thumb_tip, finger_tip, threshold=0.05):
    distance = calculate_distance(thumb_tip, finger_tip)
    return distance < threshold


def detect_open_hand(hand_landmarks):
    index_tip = (hand_landmarks.landmark[8].x, hand_landmarks.landmark[8].y)
    middle_tip = (hand_landmarks.landmark[12].x, hand_landmarks.landmark[12].y)
    ring_tip = (hand_landmarks.landmark[16].x, hand_landmarks.landmark[16].y)
    pinky_tip = (hand_landmarks.landmark[20].x, hand_landmarks.landmark[20].y)

    # Check if all fingers are extended (the tips are higher than the bases)
    index_extended = index_tip[1] < hand_landmarks.landmark[6].y
    middle_extended = middle_tip[1] < hand_landmarks.landmark[10].y
    ring_extended = ring_tip[1] < hand_landmarks.landmark[14].y
    pinky_extended = pinky_tip[1] < hand_landmarks.landmark[18].y

    return index_extended and middle_extended and ring_extended and pinky_extended


# New function to detect swipe gesture
def detect_swipe(hand_landmarks, swipe_history, swipe_threshold=0.15, frames_threshold=10):
    # Get wrist position (base of the hand)
    wrist = (hand_landmarks.landmark[0].x, hand_landmarks.landmark[0].y)

    # Add current position to history
    swipe_history.append(wrist)

    # Keep only the recent positions
    if len(swipe_history) > frames_threshold:
        swipe_history.pop(0)

    # Need enough frames to detect a swipe
    if len(swipe_history) < frames_threshold:
        return None

    # Calculate total horizontal movement
    start_x = swipe_history[0][0]
    end_x = swipe_history[-1][0]
    horizontal_movement = end_x - start_x

    # Check if the movement exceeds the threshold
    if abs(horizontal_movement) > swipe_threshold:
        # Clear history after detecting a swipe
        swipe_history.clear()

        # Return swipe direction: "right" for positive movement, "left" for negative
        return "right" if horizontal_movement > 0 else "left"

    return None


# Function to move window between monitors using GNOME's wmctrl
def move_window_to_monitor(direction):
    try:
        # Get active window ID
        active_window = subprocess.check_output(["xdotool", "getactivewindow"]).decode().strip()

        # Get current window position and size
        window_info = subprocess.check_output(["xdotool", "getwindowgeometry", active_window]).decode()

        # For GNOME on Fedora, we can use wmctrl to move the window
        if direction == "right":
            # Move to right monitor (add screen width to x-position)
            subprocess.run(["wmctrl", "-ir", active_window, "-e", f"0,{SCREEN_WIDTH},0,-1,-1"])
        else:  # left
            # Move to left monitor (set x-position to 0)
            subprocess.run(["wmctrl", "-ir", active_window, "-e", "0,0,0,-1,-1"])

        return True
    except Exception as e:
        print(f"Error moving window: {e}")
        return False


# Open the webcam
cap = cv2.VideoCapture(0)


def enable_mouse_control(**kwargs):
    previous_position = [0, 0]  # Previous cursor position
    is_left_pinching = False  # State of the left pinch gesture
    is_right_pinching = False  # State of the right pinch gesture
    both_hands_open = False  # State for detecting both hands open
    last_both_hands_time = 0  # Last time both hands open were triggered

    # For swipe detection
    swipe_history = []
    last_swipe_time = 0
    swipe_cooldown = 1.5  # Seconds between swipe actions to prevent accidental triggers

    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break

        frame = cv2.flip(frame, 1)  # Flip the frame horizontally
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # Convert the frame to RGB

        result = hands.process(rgb_frame)  # Process the frame for hand landmarks

        if result.multi_hand_landmarks:
            hands_open_count = 0  # Count of open hands detected

            for hand_landmarks in result.multi_hand_landmarks:
                # Check for open hands
                if detect_open_hand(hand_landmarks):
                    hands_open_count += 1

                # Get index tip position for cursor movement
                index_tip = (hand_landmarks.landmark[8].x, hand_landmarks.landmark[8].y)
                move_cursor(index_tip, previous_position)  # Move the cursor

                # Check for pinch gesture with the index finger (left click)
                thumb_tip = (hand_landmarks.landmark[4].x, hand_landmarks.landmark[4].y)
                if detect_pinch(thumb_tip, index_tip):
                    if not is_left_pinching:
                        app.mouse.press(app.Button.left)  # Perform a left click action
                        is_left_pinching = True  # Update the flag to indicate pinch is in progress
                else:
                    if is_left_pinching:
                        app.mouse.release(app.Button.left)
                    is_left_pinching = False  # Reset the pinch state

                # Check for pinch gesture with the middle finger (right click)
                middle_tip = (hand_landmarks.landmark[12].x, hand_landmarks.landmark[12].y)
                if detect_pinch(thumb_tip, middle_tip):
                    if not is_right_pinching:
                        app.mouse.click(app.Button.right)  # Perform a right click action
                        is_right_pinching = True
                else:
                    if is_right_pinching:
                        pass
                    is_right_pinching = False

                # Check for swipe gesture
                current_time = time.time()
                if (current_time - last_swipe_time) > swipe_cooldown:  # Only check if cooldown has passed
                    swipe_direction = detect_swipe(hand_landmarks, swipe_history)
                    if swipe_direction:
                        # Perform the swipe action
                        if move_window_to_monitor(swipe_direction):
                            print(f"Window moved to {swipe_direction} monitor")
                            last_swipe_time = current_time  # Reset cooldown timer

            current_time = time.time()
            if hands_open_count >= 2:
                if not both_hands_open:
                    with app.keyboard.pressed(app.Key.alt):
                        app.keyboard.tap(app.Key.f4)
                    both_hands_open = True
                    last_both_hands_time = current_time
            else:
                if both_hands_open and (current_time - last_both_hands_time) > 2.5:
                    both_hands_open = False


def disable_mouse_control(**kwargs):
    cap.release()
    cv2.destroyAllWindows()


app.add_func_for_search(enable_mouse_control, disable_mouse_control)

if app.lang == "en":
    app.manager.add(
        app.Command(
            [
                "enable", "gesture", "control"
            ],
            "enable_mouse_control",
            responses=[
                "Enabling gesture mouse control, sir",
                "Gesture control activated, sir"
            ],
            equivalents=[
                ["enable", "mouse", "control"],
                ["turn", "on", "mouse", "control"],
                ["turn", "on", "gesture", "control"]
            ]
        ),
        app.Command(
            [
                "disable", "gesture", "control"
            ],
            "disable_mouse_control",
            responses=[
                "Disabling gesture mouse control, sir",
                "Gesture control disactivated, sir"
            ],
            equivalents=[
                ["disable", "mouse", "control"],
                ["turn", "off", "mouse", "control"],
                ["turn", "off", "gesture", "control"]
            ]
        )
    )
elif app.lang == "ru":
    app.manager.add(
        app.Command(
            [
                "включи", "управление", "жестами"

            ],
            "enable_mouse_control",
            responses=[
                "Включаю управление курсором с помощью жестов, сэр",
                "Ж+естовое управление активировано, сэр"
            ],
            equivalents=[
                ["включи", "жесты"],
                ["включи", "жестовое", "управление"]
            ],
            synonyms={
                "управление": ["управления", ]
            }
        ),
        app.Command(
            [
                "выключи", "управление", "жестами"
            ],
            "disable_mouse_control",
            responses=[
                "Выключаю управление курсором с помощью жестов, сэр",
                "Ж+естовое управление отключено, сэр"
            ],
            equivalents=[
                ["выключи", "жесты"],
                ["выключи", "жестовое", "управление"]
            ],
            synonyms={
                "управление": ["управления", ]
            }
        )
    )