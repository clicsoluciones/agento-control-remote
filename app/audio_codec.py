import ctypes
import ctypes.util
import logging
from typing import List

logger = logging.getLogger("audio_codec")

OPUS_APPLICATION_VOIP = 2048


class OpusEncoder:
    """
    Encodes 16 kHz 16-bit mono PCM into standard Xiaozhi-compatible 60ms Opus frames (960 samples).
    """
    def __init__(self, sample_rate: int = 16000, channels: int = 1, frame_duration_ms: int = 60):
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_size = int(sample_rate * (frame_duration_ms / 1000.0))  # 960 samples for 60ms
        self.bytes_per_frame = self.frame_size * 2  # 16-bit PCM = 2 bytes/sample (1920 bytes)
        self.buffer = bytearray()

        self._lib = self._load_library()
        self._setup_bindings()
        err = ctypes.c_int(0)
        self._encoder = self._lib.opus_encoder_create(
            ctypes.c_int32(self.sample_rate),
            ctypes.c_int(self.channels),
            ctypes.c_int(OPUS_APPLICATION_VOIP),
            ctypes.byref(err)
        )
        if err.value != 0 or not self._encoder:
            raise RuntimeError(f"Failed to initialize libopus encoder: code {err.value}")

    def _setup_bindings(self):
        self._lib.opus_encoder_create.argtypes = [
            ctypes.c_int32,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
        ]
        self._lib.opus_encoder_create.restype = ctypes.c_void_p

        self._lib.opus_encode.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_int16),
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_int32,
        ]
        self._lib.opus_encode.restype = ctypes.c_int32

        self._lib.opus_encoder_destroy.argtypes = [ctypes.c_void_p]
        self._lib.opus_encoder_destroy.restype = None

    def _load_library(self) -> ctypes.CDLL:
        candidates = ["libopus.so.0", "libopus.so", "opus"]
        found = ctypes.util.find_library("opus")
        if found:
            candidates.insert(0, found)
        for name in candidates:
            try:
                return ctypes.CDLL(name)
            except Exception:
                continue
        raise RuntimeError("libopus not found on system. Install libopus0.")

    def encode_pcm(self, pcm_bytes: bytes) -> List[bytes]:
        """
        Appends incoming PCM bytes and encodes complete 60ms frames into Opus packets.
        """
        self.buffer.extend(pcm_bytes)
        packets = []

        while len(self.buffer) >= self.bytes_per_frame:
            frame_raw = bytes(self.buffer[:self.bytes_per_frame])
            del self.buffer[:self.bytes_per_frame]

            pcm_arr = (ctypes.c_int16 * self.frame_size).from_buffer_copy(frame_raw)
            out_buf = (ctypes.c_ubyte * 1024)()
            n = self._lib.opus_encode(
                self._encoder,
                pcm_arr,
                ctypes.c_int(self.frame_size),
                out_buf,
                ctypes.c_int32(1024)
            )
            if n > 0:
                packets.append(bytes(out_buf[:n]))

        return packets

    def flush(self) -> List[bytes]:
        """
        Pads any remaining partial PCM frame with silence and encodes it.
        """
        if not self.buffer:
            return []
        pad_len = self.bytes_per_frame - len(self.buffer)
        if pad_len > 0:
            self.buffer.extend(b"\x00" * pad_len)
        return self.encode_pcm(b"")

    def reset(self):
        self.buffer.clear()

    def __del__(self):
        if hasattr(self, "_encoder") and self._encoder and hasattr(self, "_lib"):
            try:
                self._lib.opus_encoder_destroy(self._encoder)
            except Exception:
                pass
