"""Custom architecture loader adapted from the inspected SILMA hf_inference.py."""
from pathlib import Path


def load_model(model_dir, variant="ema", device="cuda"):
    import torch
    from omegaconf import OmegaConf
    from f5_tts.model import CFM, DiT
    from f5_tts.model.utils import get_tokenizer

    if variant not in {"main", "ema"}:
        raise ValueError("SILMA variant must be main or ema")
    directory = Path(model_dir)
    config = OmegaConf.to_container(
        OmegaConf.load(directory / "config.yaml"), resolve=False
    )["model"]
    vocabulary, size = get_tokenizer(str(directory / "vocab.txt"), "custom")
    model = CFM(
        transformer=DiT(**config["arch"], text_num_embeds=size, mel_dim=100),
        mel_spec_kwargs=config["mel_spec"], vocab_char_map=vocabulary,
    )
    checkpoint = torch.load(
        directory / "model.pt", map_location="cpu", weights_only=True, mmap=True,
    )
    if variant == "ema":
        state = {
            key.removeprefix("ema_model."): value
            for key, value in checkpoint["ema_model_state_dict"].items()
            if key.startswith("ema_model.")
        }
    else:
        state = checkpoint["model_state_dict"]
    state = {
        key: value for key, value in state.items()
        if key not in {"mel_spec.mel_stft.mel_scale.fb", "mel_spec.mel_stft.spectrogram.window"}
    }
    model.load_state_dict(state, strict=True)
    return model.to(device).eval(), config
