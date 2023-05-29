import json
import os
import sys

from pydub import AudioSegment, silence

from transformations import seconds_to_sample

DATA_FOLDER = "input"

input_string = "C C# D D# E F F# G G# A A# B".split()

def fix_input_path(input_video_name):
    if os.path.isfile(input_video_name):
        return input_video_name

    input_video_name = os.path.join(DATA_FOLDER, f"{input_video_name}")
    if os.path.isfile(input_video_name):
        return input_video_name

    input_video_name += ".mp4"
    if os.path.isfile(input_video_name):
        return input_video_name

    return None


def get_file_name_meta(input_video_name):
    path, ext = os.path.splitext(input_video_name)
    base_name = os.path.basename(path)
    return base_name, ext


def audio_to_samples(audio_array, sample_rate):
    return [
        [
            int(seconds_to_sample(start / 1000, sample_rate)),
            int(seconds_to_sample(end / 1000, sample_rate)),
        ]
        for start, end in audio_array
    ]


def samples_to_dict(samples):
    dict_ = {}
    for i, (start, end) in enumerate(samples):
        dict_[input_string[i]] = {"start": start, "length": end - start}
    return dict_


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage: python video_to_json.py <video_file> [<spoken_characters>]")
        print("Examples:")
        print(f"\tpython {sys.argv[0]} thethiny")
        print(f"\tpython {sys.argv[0]} myfiles\\thethiny_low.mp4 0123456789")
        sys.exit(1)

    if len(sys.argv) > 2:
        input_string = sys.argv[2].strip()
        input_string = input_string.upper().split()
        print(f"Input String reset to: {input_string}")

    input_video_name = fix_input_path(sys.argv[1].strip())
    if input_video_name is None:
        print("Could not find video file")
        sys.exit(1)

    actor, extension = get_file_name_meta(input_video_name)
    extension = extension.strip(".").lower()

    print(f"Loading video: {input_video_name}")
    print(f"Actor -> {actor}")

    myaudio = AudioSegment.from_file(input_video_name, extension) + 5
    sample_rate = myaudio.frame_rate
    dBFS = myaudio.dBFS

    print(f"Sample Rate: {sample_rate}")
    print(f"dBFS: {dBFS}")

    audio_info = silence.detect_nonsilent(
        myaudio, min_silence_len=250, silence_thresh=dBFS - 16
    )
    audio_info = audio_to_samples(audio_info, sample_rate)

    if len(audio_info) != len(input_string):
        print(
            f"Error: Audio length ({len(audio_info)}) does not match input string length ({len(input_string)})"
        )
        print(input_string)
        print(
            "Please make sure that your input string is correct and that the audio is loud and clear"
        )
        sys.exit(1)

    audio_json = samples_to_dict(audio_info)

    with open(f"./{DATA_FOLDER}/{actor}.json", "w") as f:
        json.dump(audio_json, f, indent=4, ensure_ascii=False)
