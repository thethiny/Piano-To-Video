import json
from mido import MidiFile, bpm2tempo, tempo2bpm
import os
import re
import sys

NOTES_ALPHABET = "C C# D D# E F F# G G# A A# B".split()
def note_idx_to_str(note: int):
    # Note 0 is C0
    # Note 12 is C1
    # Note 24 is C2
    note_letter = NOTES_ALPHABET[note % 12]
    note_octave = note // 12
    return f"{note_letter}{note_octave}"
    
def parse_midi_file(midi_path):
    if not os.path.isfile(midi_path):
        midi_file, _ = os.path.splitext(midi_path)
        midi_file = f"midi/{midi_file}.mid"
        midi = MidiFile(midi_file)
    else:
        midi = MidiFile(midi_path)
    bpm: int = 0
    note_length: int = 0
    clocks: int = 0
    numerator: int = 0
    track_notes = {}
    
    for i, track in enumerate(midi.tracks):
        print('Track {}: {}'.format(i, track.name))
        messages = []
        for msg in track:
            messages.append(msg.dict())
            if msg.type == 'set_tempo':
                bpm = tempo2bpm(msg.tempo)
                print(f"BPM: {bpm}")
                continue
            if msg.type == 'time_signature':
                clocks = msg.clocks_per_click
                numerator = msg.numerator
                note_length = clocks * numerator
                print(f"Each note is {note_length} clocks long, consisting of {numerator} clicks of size {clocks} each")
                continue
            if msg.type == 'note_on' or msg.type == "note_off":
                track_notes.setdefault(track.name, []).append(msg)
        print(f"Track {i} has {len(messages)} messages")
        with open(f"debug/{midi_path}_track_{i}.json", "w", encoding='utf-8') as f:
            json.dump(messages, f, ensure_ascii=False, indent=4)

    # return int(bpm), int(note_length), track_notes, clocks
    return int(bpm), int(clocks), int(numerator), track_notes

def get_separators(count, split_size):
    """
    return a string of commas split by newline for every time count is greater than split_size
    """
    count = int(count)
    if count <= 0:
        return ""
    string = ","*count
    if count >= split_size:
        string = string[:-1] + "\n"
    return string

def get_track_notes(track_messages, note_length, separator_size):
    # BEAT_SIZE = 4
    text_string = ""
    last_note_type = None
    for note in track_messages:
        if note.type == "note_off":
            note_time = (note.time / note_length)
            if last_note_type == "note_on":
                note_time -= 1
            text_string += get_separators(note_time, separator_size)
            last_note_type = "note_off"
            continue
        if note.type != "note_on":
            continue
        
        # Remove duplicate notes if previous note was note_on. I cannot handle multiple note_on at the same time
        if last_note_type == "note_on" and note.time == 0: # Duplicate note
            continue
        
        note_time = note.time / note_length
        note_time = int(note_time)

        if last_note_type == "note_on":
            note_time -= 1

        text_string += get_separators(note_time, separator_size)
        text_string += f"{note_idx_to_str(note.note)},"

        last_note_type = "note_on"
        
    return text_string

def normalize_note_octaves(notes):
    """
    Reads the notes and shifts them all to start at Octave 1, and remove 1 from the note
    """
    notes_pattern = re.compile(r'(?:[A-G][#]?)([0-9]{1,2})')
    # Get octaves using regex
    octaves = notes_pattern.findall(notes)
    # Get the lowest octave
    lowest_octave = int(min(octaves)) - 1
    # Shift all octaves to start at 1
    notes = re.sub(r'([0-9]{1,2})', lambda x: str(int(x.group())-lowest_octave), notes)

    # Remove 0 from all notes
    notes = re.sub(r'([A-G][#]?)(?:1)', r'\1', notes)

    return notes

    
if __name__ == "__main__":
    midi_file = sys.argv[1] if (len(sys.argv) > 1) else "test.mid"
    if len(sys.argv) > 2:
        separator_size_user = float(sys.argv[2])
    else:
        separator_size_user = None
    bpm, clock_size, numerator, track_notes = parse_midi_file(midi_file)
    for track in track_notes:
        print(track)

        if separator_size_user is not None:
            beat_size = (numerator**2) / separator_size_user
            separator_size = separator_size_user
            lowest_clock = beat_size * clock_size
        else:
            times = {note.time for note in track_notes[track] if note.time % clock_size == 0} # Get all times that are a multiple of the note length
            times.discard(0) # Discord notes with no time
            lowest_clock = min(times) # Multiple of clock_size

            beat_size: float = (lowest_clock / clock_size)# Beats per clock 
            separator_size = (numerator**2) / (beat_size)

        notes = get_track_notes(track_notes[track], lowest_clock, separator_size)
        notes = normalize_note_octaves(notes)
        
        note_file = os.path.splitext(midi_file)[0] + f"_{track}.txt"
        with open(note_file, "w") as f:
            f.write(f"{int(bpm)} {separator_size}\n")
            f.write(notes)

