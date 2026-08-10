import math
import time
import board
import displayio
import terminalio
import digitalio
import usb_hid
from adafruit_display_text import label
import adafruit_displayio_ssd1306
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.consumer_control_code import ConsumerControlCode

try:
    from i2cdisplaybus import I2CDisplayBus
except ImportError:
    from displayio import I2CDisplay as I2CDisplayBus

displayio.release_displays()

i2c = board.I2C()
display_bus = I2CDisplayBus(i2c, device_address=0x3C)

WIDTH = 128
HEIGHT = 32

display = adafruit_displayio_ssd1306.SSD1306(display_bus, width=WIDTH, height=HEIGHT, rotation=0)

splash = displayio.Group()
display.root_group = splash

# --- UI LABELS SETUP ---
layer_label = label.Label(terminalio.FONT, text="N", color=0xFFFFFF)
layer_label.x = 100
layer_label.y = 8
splash.append(layer_label)

mode_label = label.Label(terminalio.FONT, text="VOL", color=0xFFFFFF)
mode_label.x = 100
mode_label.y = 24
splash.append(mode_label)

grid_labels = []
coords = [(10, 8), (52, 8), (10, 24), (52, 24)]
for coord in coords:
    lbl = label.Label(terminalio.FONT, text="-", color=0xFFFFFF)
    lbl.x = coord[0]
    lbl.y = coord[1]
    splash.append(lbl)
    grid_labels.append(lbl)

# --- HID & INPUT SETUP ---
kbd = Keyboard(usb_hid.devices)
cc = ConsumerControl(usb_hid.devices)

# Switches S1-S5 mapped to D0, D1, D2, D3, TX
switch_pins = [board.D0, board.D1, board.D2, board.D3, board.TX]
switches = []
for pin in switch_pins:
    sw = digitalio.DigitalInOut(pin)
    sw.direction = digitalio.Direction.INPUT
    sw.pull = digitalio.Pull.UP
    switches.append(sw)

last_switch_states = [True] * len(switches)

# Rotary Encoder Push Button (SW6) on RX
encoder_button = digitalio.DigitalInOut(board.RX)
encoder_button.direction = digitalio.Direction.INPUT
encoder_button.pull = digitalio.Pull.UP
last_button_state = True

# Software Rotary Encoder Pins on D8 and D9
enc_a = digitalio.DigitalInOut(board.D8)
enc_a.direction = digitalio.Direction.INPUT
enc_a.pull = digitalio.Pull.UP

enc_b = digitalio.DigitalInOut(board.D9)
enc_b.direction = digitalio.Direction.INPUT
enc_b.pull = digitalio.Pull.UP

last_a_state = enc_a.value

# --- LAYER & MODE STATE ---
current_layer = 0
layer_key_index = 2
last_layer_key_state = True

# Double-click tracking variables
click_count = 0
first_click_time = 0.0
double_click_window = 0.35  # Max seconds between taps for a double-click

control_mode = "VOLUME"

# Layer display names mapped to N, M, S, F
layer_names_list = ["N", "M", "S", "F"]

# 4 Layers of key mappings and display names:
# Order for keys/names: [S1, S2, S4, S5, Encoder Button]
layer_data = [
    {
        "keys": [
            [Keycode.LEFT_GUI, Keycode.Z],                       # S1: Cmd + Z
            [Keycode.LEFT_GUI, Keycode.LEFT_SHIFT, Keycode.Z],   # S2: Cmd + Shift + Z
            [Keycode.LEFT_GUI, Keycode.SPACE],                   # S3: Cmd + Space
            [Keycode.LEFT_GUI, Keycode.TAB],                     # S4: Cmd + Tab
            [Keycode.LEFT_GUI]                                   # Encoder Button
        ],
        "names": ["Undo", "Redo", "Spot", "Tab"]
    },
    {
        "keys": [
            [Keycode.LEFT_GUI, Keycode.Z],                       # S1: Cmd + Z
            [Keycode.LEFT_GUI, Keycode.LEFT_SHIFT, Keycode.Z],   # S2: Cmd + Shift + Z
            [Keycode.LEFT_GUI, Keycode.S],                       # S3: Cmd + S
            [Keycode.LEFT_GUI, Keycode.LEFT_CONTROL, Keycode.F], # S4: Cmd + Ctrl + F
            [Keycode.LEFT_GUI]                                   # Encoder Button
        ],
        "names": ["Undo", "Redo", "Save", "Full"]
    },
    {
        "keys": [
            [Keycode.LEFT_GUI, Keycode.W],                       # S1: Cmd + W
            [Keycode.LEFT_GUI, Keycode.N],                       # S2: Cmd + N
            [Keycode.LEFT_GUI, Keycode.ONE],                     # S3: Cmd + 1
            [Keycode.LEFT_GUI, Keycode.LEFT_SHIFT, Keycode.L],   # S4: Shift + Cmd + L
            [Keycode.LEFT_GUI]                                   # Encoder Button
        ],
        "names": ["Close", "New", "First", "Side"]
    },
    {
        "keys": [
            [Keycode.L],                                         # S1: L
            [Keycode.D],                                         # S2: D
            [Keycode.LEFT_GUI, Keycode.S],                       # S3: Cmd + S
            [Keycode.ENTER],                                     # S4: Enter
            [Keycode.LEFT_GUI]                                   # Encoder Button
        ],
        "names": ["Line", "Dime", "Save", "Enter"]
    },
]

def update_display_text():
    layer_label.text = layer_names_list[current_layer]
    mode_label.text = "VOL" if control_mode == "VOLUME" else "BRI"
    
    active_names = layer_data[current_layer]["names"]
    grid_labels[0].text = active_names[0]
    grid_labels[1].text = active_names[1]
    grid_labels[2].text = active_names[2]
    grid_labels[3].text = active_names[3]

update_display_text()

while True:
    # 2. Check Layer Switch (D2 / index 2) with Double-Click logic
    current_layer_key_state = switches[layer_key_index].value
    if last_layer_key_state and not current_layer_key_state:
        # Button was just pressed down
        now = time.monotonic()
        if click_count == 0:
            click_count = 1
            first_click_time = now
        elif click_count == 1:
            if (now - first_click_time) <= double_click_window:
                # Double click detected: Go backward 1 layer
                current_layer = (current_layer - 1) % 4
                print(f"Double Click! Switched backward to Layer: {layer_names_list[current_layer]}")
                update_display_text()
                click_count = 0
            else:
                # Too slow, treat this press as the start of a new single click
                click_count = 1
                first_click_time = now
    last_layer_key_state = current_layer_key_state

    # Check if the single-click window has expired to execute forward step
    if click_count == 1 and (time.monotonic() - first_click_time) > double_click_window:
        current_layer = (current_layer + 1) % 4
        print(f"Single Click! Switched forward to Layer: {layer_names_list[current_layer]}")
        update_display_text()
        click_count = 0

    # 3. Check S1, S2, S4, S5 Switches using current layer mapping
    active_layer_info = layer_data[current_layer]
    active_keys = active_layer_info["keys"]
    
    for i, sw in enumerate(switches):
        if i == layer_key_index:
            continue
            
        current_state = sw.value
        map_idx = i if i < 2 else i - 1
        
        if last_switch_states[i] and not current_state:
            for k in active_keys[map_idx]:
                kbd.press(k)
        elif not last_switch_states[i] and current_state:
            for k in active_keys[map_idx]:
                kbd.release(k)
        last_switch_states[i] = current_state

    # 4. Check Rotary Encoder Button Press (Toggles Mode & Types Layer Key)
    current_button_state = encoder_button.value
    if last_button_state and not current_button_state:
        if control_mode == "VOLUME":
            control_mode = "BRIGHTNESS"
            print("Control Mode: COMPUTER BRIGHTNESS")
        else:
            control_mode = "VOLUME"
            print("Control Mode: VOLUME")
            
        update_display_text()
        for k in active_keys[4]:
            kbd.press(k)
    elif not last_button_state and current_button_state:
        for k in active_keys[4]:
            kbd.release(k)
    last_button_state = current_button_state

    # 5. Check Software Rotary Encoder Rotation (Volume or Computer Brightness)
    current_a_state = enc_a.value
    if last_a_state and not current_a_state:
        direction = 1 if enc_b.value else -1
        
        if control_mode == "VOLUME":
            if direction > 0:
                cc.send(ConsumerControlCode.VOLUME_INCREMENT)
            else:
                cc.send(ConsumerControlCode.VOLUME_DECREMENT)
        elif control_mode == "BRIGHTNESS":
            if direction > 0:
                cc.send(ConsumerControlCode.BRIGHTNESS_INCREMENT)
            else:
                cc.send(ConsumerControlCode.BRIGHTNESS_DECREMENT)
            
    last_a_state = current_a_state

    time.sleep(0.005)
