import librosa
import numpy
from moviepy.audio.AudioClip import AudioArrayClip


def sample_to_seconds(sample, sample_rate):
    return sample / sample_rate


def seconds_to_sample(seconds, sample_rate):
    return seconds * sample_rate


# Test Change Pitch
def shift_pitch_audio(audio_array, steps):
    audio_left = audio_array[:, 0]
    audio_right = audio_array[:, 1]
    y_shifted_l = librosa.effects.pitch_shift(audio_left, 48000, n_steps=steps)
    y_shifted_r = librosa.effects.pitch_shift(audio_right, 48000, n_steps=steps)
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
