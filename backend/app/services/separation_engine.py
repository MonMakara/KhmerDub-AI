"""Private subprocess entrypoint for the isolated Demucs Python environment.

Only local, administrator-installed weights are used. Never downloads models.
Processes bounded overlapped windows and reuses one model throughout the task.
"""
import argparse
import json
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("voice", type=Path)
    parser.add_argument("background", type=Path)
    parser.add_argument("result", type=Path)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "auto", "cuda"], default="cpu")
    parser.add_argument("--strength", choices=["light", "balanced", "strong"], default="balanced")
    args = parser.parse_args()
    import numpy as np
    import soundfile as sf
    import torch

    # Ensure compatibility with PyTorch 2.6+ default weights_only=True
    _orig_load = torch.load
    def _compat_load(*load_args, **load_kwargs):
        if "weights_only" not in load_kwargs:
            load_kwargs["weights_only"] = False
        return _orig_load(*load_args, **load_kwargs)
    torch.load = _compat_load

    from demucs.apply import apply_model
    from demucs.pretrained import get_model
    from torchaudio.functional import resample

    torch.set_num_threads(2)
    print(json.dumps({"phase": "Loading separation model", "progress": 0}), flush=True)
    # Passing a local repository prevents get_model from using the remote zoo.
    model = get_model("955717e8", repo=args.repo)
    model.eval()
    device = "cpu"
    if args.device != "cpu" and torch.cuda.is_available():
        free, _ = torch.cuda.mem_get_info()
        if free > 5.5 * 1024**3:
            device = "cuda"
    model.to(device)
    blend = {"light": .4, "balanced": .2, "strong": .05}[args.strength]
    peak = 0.0
    completed = 0
    fallback = False
    with sf.SoundFile(args.source) as source, sf.SoundFile(args.voice, "w", samplerate=source.samplerate,
          channels=source.channels, subtype="FLOAT") as voice_file, sf.SoundFile(args.background, "w",
          samplerate=source.samplerate, channels=source.channels, subtype="FLOAT") as background_file:
        rate = source.samplerate
        total = len(source)
        window, hop, context = 20*rate, 18*rate, 2*rate
        previous = None
        previous_background = None
        for start in range(0, total, hop):
            left = max(0, start-context)
            right = min(total, start+window+context)
            source.seek(left)
            samples = source.read(right-left, dtype="float32", always_2d=True)
            tensor = torch.from_numpy(samples.T.copy())
            if tensor.shape[0] == 1:
                tensor = tensor.repeat(2, 1)
            tensor = resample(tensor, rate, model.samplerate)
            mean = tensor.mean()
            std = tensor.std().clamp(min=1e-6)
            normalized = (tensor-mean)/std

            def infer(target):
                with torch.inference_mode():
                    return apply_model(model, normalized[None].to(target), device=target,
                                       shifts=0, split=True, overlap=.25, segment=5,
                                       progress=False, num_workers=0)[0].cpu()

            try:
                stems = infer(device)
            except RuntimeError as exc:
                if device != "cuda" or "out of memory" not in str(exc).lower():
                    raise
                model.to("cpu")
                torch.cuda.empty_cache()
                device, fallback = "cpu", True
                stems = infer(device)
            vocal = stems[model.sources.index("vocals")] * std + mean
            vocal = resample(vocal, model.samplerate, rate).numpy().T
            if source.channels == 1:
                vocal = vocal.mean(axis=1, keepdims=True)
            # Resampling can differ by one frame; padding preserves the timeline.
            if len(vocal) < len(samples):
                vocal = np.pad(vocal, ((0,len(samples)-len(vocal)),(0,0)))
            vocal = vocal[:len(samples)]
            offset = start-left
            count = min(window, total-start)
            original = samples[offset:offset+count]
            vocal = vocal[offset:offset+count]
            residual = original-vocal
            vocal += blend*residual
            if previous is not None:
                overlap = min(len(previous), len(vocal))
                weights = np.linspace(0,1,overlap, dtype=np.float32)[:,None]
                vocal[:overlap] = previous[:overlap]*(1-weights)+vocal[:overlap]*weights
                residual[:overlap] = previous_background[:overlap]*(1-weights)+residual[:overlap]*weights
            last = start+window >= total
            count_write = len(vocal) if last else hop
            data, backing = vocal[:count_write], residual[:count_write]
            peak = max(peak, float(np.max(abs(data))), float(np.max(abs(backing))))
            voice_file.write(data)
            background_file.write(backing)
            completed += len(data)
            previous, previous_background = vocal[hop:].copy(), residual[hop:].copy()
            print(json.dumps({"phase":"Separating speech and music", "progress":round(completed/total*100),
                              "device":device}), flush=True)
            if last:
                break
        if completed != total:
            raise RuntimeError("Separated output frame coverage does not match input")
    args.result.write_text(json.dumps({"engine":"Demucs 4.0.1 / htdemucs 955717e8",
        "device":device, "cpu_fallback":fallback, "model_sample_rate":model.samplerate,
        "retained_background_fraction":blend, "peak_before_gain":peak,
        "output_gain":min(1.0, .98/max(peak,1e-9)), "covered_frames":completed}))


if __name__ == "__main__":
    main()
