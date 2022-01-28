import json
import os
import re
from functools import partial
from multiprocessing.pool import ThreadPool
from sys import argv
from threading import local

import librosa
import moviepy.editor as mp
import numpy
from moviepy.audio.AudioClip import AudioArrayClip
from moviepy.editor import ColorClip
from moviepy.video.io.VideoFileClip import VideoFileClip
from proglog import TqdmProgressBarLogger
from tqdm import tqdm

from consts import codecs

MOVIEPY_LOGGER = TqdmProgressBarLogger(print_messages=False)
CACHING = os.environ.get("CACHING", "false").lower() == "true"
CODEC = "mp4_alt"
shift_cache = {}


def sample_to_seconds(sample, sample_rate):
    return sample / sample_rate


def mapping_to_timestamps(mapping, sample_rate):
    start = mapping["start"]
    end = mapping["length"] + start
    return sample_to_seconds(start, sample_rate), sample_to_seconds(end, sample_rate)


def get_note_video(
    mapping_data, note_data, input_video: VideoFileClip, sample_rate=48000
):
    note, note_duration = note_data["note"], note_data["duration"]
    ###
    find_note = mapping_data.get(note, None)
    shift_amount = 0
    if find_note is None:
        # Have to pitch shift
        found = re.findall(r"([A-G][#]?) ?([0-9]{0,2})", note)
        if not found:
            raise Exception(f"Could not find note: {note}")
        found = found[0]
        note_ = found[0].strip()
        octave = int(found[1].strip()) if found[1].strip() else 1
        find_note_up = find_note_down = None
        make_note_up = make_note_down = None
        i = 1
        while find_note_up is None and find_note_down is None:
            # shift_up = (octave+i)%10
            # if shift_up == 0:
            #     shift_up = 1
            # shift_down = (octave-i)%10
            # if shift_down == 0:
            #     shift_down = 9
            # Need to rework shift because rotations are not allowed
            shift_up = octave + i
            shift_down = octave - i

            make_note_up = f"{note_}{shift_up}" if shift_up != 1 else note_
            make_note_down = f"{note_}{shift_down}" if shift_down != 1 else note_
            find_note_up = mapping_data.get(make_note_up, None)
            find_note_down = mapping_data.get(make_note_down, None)
            i += 1
        if find_note_up:
            shift_amount = (-i) + 1
            find_note = make_note_up
        elif find_note_down:
            shift_amount = i - 1
            find_note = make_note_down
        else:
            raise Exception(f"Could not find base for note {note}")

    else:
        find_note = note
    ###
    start, end = mapping_to_timestamps(mapping_data[find_note], sample_rate)
    note_video: VideoFileClip
    if (
        CACHING
    ):  # If caching is enabled then caching is done on the whole video, else it is done on the note clip
        if shift_amount:
            if shift_cache.get(find_note, {}).get(shift_amount, None) is None:
                note_video = input_video.subclip(start, end)
                shift_cache[find_note] = {}
                shift_cache[find_note][shift_amount] = shift_pitch(
                    note_video, shift_amount
                )
            note_video = shift_cache[find_note][shift_amount]
        else:
            note_video = input_video.subclip(start, end)
    else:
        note_video = input_video.subclip(start, end)

    # video_duration = end - start
    video_duration = note_video.duration
    start = 0  # Start of the note_video
    black_fill = None
    if not note:
        # Replace this section with blank note video
        video_duration = 0
        end = start
    if video_duration < note_duration:
        # Add green screen fill
        black_fill = ColorClip(
            size=input_video.size,
            color=(0, 255, 0),
            duration=note_duration - video_duration,
        )
        black_fill.set_fps(input_video.fps)
        end = start + video_duration
    else:
        end = start + note_duration

    video = note_video.subclip(start, end)
    if not CACHING:
        video = shift_pitch(video, shift_amount) if shift_amount else video
    # video = input_video.subclip(start, end)
    # video = shift_pitch(video, shift_amount) if shift_amount else video
    # Can't cache video clips because the duration changes
    # if shift_amount:
    #     if shift_cache.get(find_note, {}).get(shift_amount, None) is None:
    #         shift_cache[find_note] = {}
    #         video = shift_cache[find_note][shift_amount] = shift_pitch(video, shift_amount)
    #     else:
    #         video = shift_cache[find_note][shift_amount]
    #         # print("Cache", end="\r")

    #     # video = shift_pitch(video, shift_amount)

    if black_fill:
        video = mp.concatenate_videoclips([video, black_fill])
    return video


def parse_notes(path):
    with open(path, "r", encoding="utf-8") as f:
        data = f.read().replace("-", ",").replace("–", ",")
    tempo, notes = data.split("\n", 1)
    tempo = tempo.split(" ")
    if not tempo:
        raise Exception("Could not find tempo information")
    bpm = int(tempo[0].strip())
    if len(tempo) == 1:  # Compatibility
        beat_size = 4.0
    else:
        beat_size = float(tempo[1].strip())
    bps = bpm / 60 * beat_size
    notes_data = []
    for line in notes.split("\n"):
        notes_data += [n.strip().upper() for n in line.split(",")]
    note_duration = 1 / bps
    all_notes = {}
    last_note = 0
    for note in notes_data:
        if not note:
            if not last_note:
                last_note += 1
                all_notes[last_note - 1] = {"note": "", "duration": note_duration}
                continue
            all_notes[last_note - 1]["duration"] += note_duration
            continue
        all_notes[last_note] = {"note": note, "duration": note_duration}
        last_note += 1
    return bpm, beat_size, all_notes


FFMPEG_BINARY_AAC = "ffmpeg.exe"
OUTPUT_FOLDER = "output"
SONGS_FOLDER = "songs"
DATA_FOLDER = "input"

if len(argv) < 3:
    print(f"Usage: python {argv[0]} <input_name> <song_name>")
    exit()

input_video_path = os.path.join(DATA_FOLDER, f"{argv[1]}.mp4")
input_notes_path = os.path.join(SONGS_FOLDER, f"{argv[2]}.txt")
mappings_path = os.path.join(DATA_FOLDER, f"{argv[1]}.json")

with open(mappings_path, "r") as f:
    mappings = json.load(f)

bpm, beat_size, notes = parse_notes(input_notes_path)


input_video = VideoFileClip(input_video_path)
# Test Change Pitch
def shift_pitch_audio(audio_array, octaves):
    audio_left = audio_array[:, 0]
    audio_right = audio_array[:, 1]
    y_shifted_l = librosa.effects.pitch_shift(audio_left, 48000, n_steps=octaves * 12)
    y_shifted_r = librosa.effects.pitch_shift(audio_right, 48000, n_steps=octaves * 12)
    # Create stereo audio
    y_shifted = numpy.stack((y_shifted_l, y_shifted_r), axis=1)
    return y_shifted


def shift_pitch(clip, octaves):
    audio = clip.audio.set_fps(48000)
    audio_array = audio.to_soundarray()
    y_shifted = shift_pitch_audio(audio_array, octaves)
    # Create AudioClip from numpy array
    audio_shifted = AudioArrayClip(y_shifted, fps=48000).set_fps(48000)
    clip.audio = audio_shifted
    return clip


# input_video.audio = audio = input_video.audio.set_fps(48000) # type: ignore
# sample_rate = audio.fps

output_path = f"{argv[1]}_{argv[2]}_{bpm}_{beat_size}.mp4"

print(
    f"Task -> Actor: {argv[1].strip().title()} | Song: {argv[2].replace('_', ' ').strip().title()} | BPM: {bpm} | Beats: {beat_size} ({beat_size//4}/4) | {len(notes)} notes"
)
# print("Sample Rate:", sample_rate)

shared_local = local()

videos = []
note = -1


def process_note(mappings, notes, video_path, note):
    if not hasattr(shared_local, "video") or not shared_local.video:
        shared_local.video = in_video = VideoFileClip(video_path)
        shared_local.video.audio = in_video.audio.set_fps(48000)  # type: ignore
        shared_local.sample_rate = shared_local.video.audio.fps  # type: ignore

    return get_note_video(
        mappings, notes[note], shared_local.video, shared_local.sample_rate
    )


pool = ThreadPool(6)
process_note_partial = partial(process_note, mappings, notes, input_video_path)
results = tqdm(
    pool.imap(process_note_partial, notes.keys()), desc="Notes", total=len(notes)
)
videos = list(results)

# videos = pool.map(process_note_partial, notes.keys())
# for note in tqdm(notes, desc="Notes"):
#     video = get_note_video(mappings, notes[note], input_video, sample_rate)
#     videos.append(video)

concat_clip = mp.concatenate_videoclips(videos)

output_path_folder = os.path.join(OUTPUT_FOLDER, argv[1].strip())
if not os.path.exists(output_path_folder):
    os.makedirs(output_path_folder)
out_file = os.path.join(output_path_folder, output_path).replace('/', '\\')


print(f"Saving to {out_file}")
print("Duration: {:.2f}".format(concat_clip.duration))
concat_clip.write_videofile(
    out_file,
    codec=codecs[CODEC]["codec"],
    audio_codec=codecs[CODEC]["audio_codec"],
    logger=MOVIEPY_LOGGER,
    threads=6,
)

os.startfile(out_file)
