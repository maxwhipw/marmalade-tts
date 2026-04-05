"""Engine base class and registry."""


class Engine:
    """Base class for TTS engines."""

    name: str = ""

    def synthesize(self, text: str, out_path: str, **kwargs):
        """Synthesize text to a WAV file. Subclasses must implement."""
        raise NotImplementedError

    def list_voices(self):
        """Print available voices/models. Subclasses should override."""
        print(f"[{self.name}] No voice listing available.")
