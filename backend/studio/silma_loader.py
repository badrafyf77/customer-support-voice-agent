"""Compatibility entrypoint for the phase 1 load probe."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'code'))
from core.nodes.tts.silma_model import load_model
