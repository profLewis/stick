# notes.py -- Note name -> (frequency_hz, midi_note_number)
#
# Naming matches WAV filenames: C4, Cs4 (C#4), D4, Ds4 (D#4), etc.
# Frequencies: A4 = 440 Hz, equal temperament.
# MIDI: C4 = 60 ... E6 = 88

NOTES = {
    "C4":  (261.63, 60),
    "Cs4": (277.18, 61),
    "D4":  (293.66, 62),
    "Ds4": (311.13, 63),
    "E4":  (329.63, 64),
    "F4":  (349.23, 65),
    "Fs4": (369.99, 66),
    "G4":  (392.00, 67),
    "Gs4": (415.30, 68),
    "A4":  (440.00, 69),
    "As4": (466.16, 70),
    "B4":  (493.88, 71),
    "C5":  (523.25, 72),
    "Cs5": (554.37, 73),
    "D5":  (587.33, 74),
    "Ds5": (622.25, 75),
    "E5":  (659.26, 76),
    "F5":  (698.46, 77),
    "Fs5": (739.99, 78),
    "G5":  (783.99, 79),
    "Gs5": (830.61, 80),
    "A5":  (880.00, 81),
    "As5": (932.33, 82),
    "B5":  (987.77, 83),
    "C6":  (1046.50, 84),
    "Cs6": (1108.73, 85),
    "D6":  (1174.66, 86),
    "Ds6": (1244.51, 87),
    "E6":  (1318.51, 88),
}


def freq(name):
    """Return frequency in Hz for a note name, or None."""
    entry = NOTES.get(name)
    return entry[0] if entry else None


def midi_note(name):
    """Return MIDI note number for a note name, or None."""
    entry = NOTES.get(name)
    return entry[1] if entry else None


def all_names():
    """Return sorted list of all note names by pitch."""
    return sorted(NOTES.keys(), key=lambda n: NOTES[n][1])
