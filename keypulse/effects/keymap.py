"""Maps typed characters to the Everest 60 key that produces them."""

# shifted symbols live on the same key as their unshifted partner
SHIFTED = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8", "(": "9", ")": "0",
    "_": "-", "+": "=", "{": "[", "}": "]", "|": "\\", ":": ";", '"': "'", "<": ",", ">": ".", "?": "/",
    "~": "`",
}

# character -> OpenRGB key name, where they differ
NAMES = {"\\": "\\ (ANSI)", "`": "Escape"}   # the 60% board puts ` on the Escape key

# Corrections for keys whose OpenRGB name doesn't match the physical key on the Everest 60.
# From a physical check with tools/keyprobe.py (2026-11-16, ANSI Everest 60, firmware 1.45):
# {"name OpenRGB uses": "key that actually lights"}. The matrix *positions* are right; only these names are swapped.
# (The / key may show solid white regardless: that's the keyboard firmware using it as a status indicator.)
CORRECTIONS: dict = {"B": "V", "V": "B"}


def key_name(ch: str):
    """Return the OpenRGB key name for a character, or None if it isn't on the keyboard (spaces included)."""
    if not ch or ch.isspace():
        return None
    ch = SHIFTED.get(ch, ch)
    if ch.isalpha():
        ch = ch.upper()
        if not ("A" <= ch <= "Z"):
            return None
    return NAMES.get(ch, ch)


def led_for(ch: str, key_leds: dict):
    name = key_name(ch)
    if name is None:
        return None
    # if OpenRGB's label for this LED is wrong, find the LED labelled with the key that really lights here
    for label, actual in CORRECTIONS.items():
        if actual == name:
            name = label
            break
    return key_leds.get(name)
