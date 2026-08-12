# SPDX-License-Identifier: GPL-3.0-or-later
"""KO6FQY field-test beacon for XIAO ESP32-C3 + NiceRF SA868.

Hardware mapping and control flow are adapted from the CircuitPython port of
the rot13labs Fox Hunt Badge by Bradan Lane STUDIO:
https://gitlab.com/bradanlane_cp/foxhunt
"""

import time

import board
import busio
import digitalio
import pwmio


CALL_MESSAGE = "KO6FQY -- decoy decoy -- KO6FQY"
FREQUENCY_MHZ = 144.3000
MESSAGE_DELAY_SECONDS = 30.0
MORSE_WPM = 13
MORSE_TONE_HZ = 800
BANDWIDTH = 1  # 0 = 12.5 kHz, 1 = 25 kHz
SQUELCH = 3
VOLUME = 5

# rot13labs badge wiring for the Seeed Studio XIAO ESP32-C3.
PTT_PIN = board.D3  # Active low
POWER_DOWN_PIN = board.D4
POWER_LEVEL_PIN = board.D5  # Low = low RF power
RADIO_TX_PIN = board.D6
RADIO_RX_PIN = board.D7
MIC_PIN = board.D1


MORSE = {
    "a": ".-", "b": "-...", "c": "-.-.", "d": "-..", "e": ".",
    "f": "..-.", "g": "--.", "h": "....", "i": "..", "j": ".---",
    "k": "-.-", "l": ".-..", "m": "--", "n": "-.", "o": "---",
    "p": ".--.", "q": "--.-", "r": ".-.", "s": "...", "t": "-",
    "u": "..-", "v": "...-", "w": ".--", "x": "-..-", "y": "-.--",
    "z": "--..", "0": "-----", "1": ".----", "2": "..---",
    "3": "...--", "4": "....-", "5": ".....", "6": "-....",
    "7": "--...", "8": "---..", "9": "----.", ".": ".-.-.-",
    ",": "--..--", "?": "..--..", "'": ".----.", "!": "-.-.--",
    "/": "-..-.", "-": "-....-", "@": ".--.-.",
}


def output_pin(pin, initial=False):
    item = digitalio.DigitalInOut(pin)
    item.direction = digitalio.Direction.OUTPUT
    item.value = initial
    return item


def radio_command(uart, command, wait_seconds=0.25):
    uart.write((command + "\r\n").encode("ascii"))
    time.sleep(wait_seconds)
    response = uart.read(128)
    print("radio", command, repr(response))
    return response


microphone_idle = None
tone_pwm = None


def initialize_tone():
    """Allocate microphone PWM once so keying preserves Morse timing."""
    global microphone_idle, tone_pwm
    if microphone_idle is not None:
        microphone_idle.deinit()
        microphone_idle = None
    if tone_pwm is None:
        tone_pwm = pwmio.PWMOut(
            MIC_PIN,
            frequency=int(MORSE_TONE_HZ),
            duty_cycle=0,
            variable_frequency=True,
        )


def tone_on(frequency_hz):
    global microphone_idle, tone_pwm
    if tone_pwm is None:
        initialize_tone()
    if int(frequency_hz) != int(MORSE_TONE_HZ):
        tone_pwm.frequency = int(frequency_hz)
    tone_pwm.duty_cycle = 32768


def tone_off():
    global microphone_idle, tone_pwm
    if tone_pwm is not None:
        tone_pwm.duty_cycle = 0
    elif microphone_idle is None:
        microphone_idle = output_pin(MIC_PIN, False)
    else:
        microphone_idle.value = False


def play_morse(message):
    unit = 1.2 / MORSE_WPM
    print("transmitting", repr(message))
    for character in message.lower():
        if character == " ":
            # The prior character already supplied a three-unit letter gap.
            time.sleep(unit * 4)
            continue
        marks = MORSE.get(character)
        if marks is None:
            continue
        for mark in marks:
            tone_on(MORSE_TONE_HZ)
            time.sleep(unit if mark == "." else unit * 3)
            tone_off()
            time.sleep(unit)
        # The last element already supplied one unit of silence.
        time.sleep(unit * 2)


print("KO6FQY field-test beacon starting")

# Establish all safety-critical levels before opening the radio UART.
ptt = output_pin(PTT_PIN, True)
power_down = output_pin(POWER_DOWN_PIN, True)
power_level = output_pin(POWER_LEVEL_PIN, False)
initialize_tone()
tone_off()

radio_uart = busio.UART(
    RADIO_TX_PIN,
    RADIO_RX_PIN,
    baudrate=9600,
    timeout=1.0,
)
time.sleep(1.0)

radio_command(radio_uart, "AT+DMOCONNECT", 0.5)
radio_command(
    radio_uart,
    "AT+DMOSETGROUP={},{:.4f},{:.4f},0000,{},0000".format(
        BANDWIDTH,
        FREQUENCY_MHZ,
        FREQUENCY_MHZ,
        SQUELCH,
    ),
    0.5,
)
radio_command(radio_uart, "AT+DMOSETVOLUME={}".format(VOLUME), 0.25)

print(
    "ready: {:.4f} MHz, low power, {} WPM".format(
        FREQUENCY_MHZ,
        MORSE_WPM,
    )
)

while True:
    try:
        ptt.value = False
        time.sleep(0.75)
        play_morse(CALL_MESSAGE)
    finally:
        # Never leave PTT active after a completed message or Python error.
        ptt.value = True
        tone_off()
    print("idle for", MESSAGE_DELAY_SECONDS, "seconds")
    time.sleep(MESSAGE_DELAY_SECONDS)
