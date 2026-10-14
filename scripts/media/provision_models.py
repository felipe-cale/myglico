"""Provision pinned local media models once; runtime never invokes this script."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--whisper", default="small")
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    whisper_dir = root / "whisper"
    import shutil

    if whisper_dir.exists():
        required = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
        if not all((whisper_dir / name).is_file() for name in required):
            raise FileExistsError("existing local Whisper model directory is incomplete")
    else:
        from faster_whisper.utils import download_model

        downloaded = Path(download_model(args.whisper, output_dir=str(root / "download-cache")))
        shutil.copytree(downloaded, whisper_dir)
    # Resolve official pretrained weights only in this explicit online
    # provisioning step, then copy them under the caller's local model root.
    # Runtime uses these explicit paths with PADDLE_PDX_MODEL_SOURCE=LOCAL.
    from paddlex.inference.utils.official_models import official_models

    for model_name, target_name in (
        ("PP-OCRv5_server_det", "paddle-det"),
        ("en_PP-OCRv5_mobile_rec", "paddle-rec"),
    ):
        target = root / target_name
        if target.exists():
            required = ("inference.json", "inference.pdiparams", "inference.yml")
            if not all((target / name).is_file() for name in required):
                raise FileExistsError(f"existing local model directory is incomplete: {target}")
            continue
        source = Path(official_models[model_name]).resolve()
        if not source.is_dir():
            raise FileNotFoundError(f"PaddleX returned no model directory for {model_name}")
        shutil.copytree(source, target)

    # Validate the copied weights offline; passing model_dir makes PaddleX use
    # the local assets and avoids downloading a second copy.
    from paddlex import create_model

    det = create_model("PP-OCRv5_server_det", model_dir=str(root / "paddle-det"))
    rec = create_model("en_PP-OCRv5_mobile_rec", model_dir=str(root / "paddle-rec"))
    del det, rec
    print(f"Provisioned local model directories under {root}; record package/model hashes before deployment.")


if __name__ == "__main__":
    main()
