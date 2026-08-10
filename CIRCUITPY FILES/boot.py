import usb_hid

# Enable both Keyboard and Consumer Control (multimedia/volume) HID devices
usb_hid.enable((usb_hid.Device.KEYBOARD, usb_hid.Device.CONSUMER_CONTROL))
