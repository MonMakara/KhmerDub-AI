"""Startup and runtime prerequisite verification for subtitle burn-in.
Ensures libass with HarfBuzz complex shaping engine and Khmer fonts are available.
"""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Set, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# Primary Khmer font families required for high-quality subtitle typography
REQUIRED_KHMER_FONTS = [
    "Khmer OS Battambang",
    "Khmer OS Content",
    "Khmer OS Muol",
    "Noto Sans Khmer",
]

_PREREQUISITES_VERIFIED: bool = False


def get_fonts_dir() -> Path:
    """Resolve the bundled or system directory containing Khmer TTF fonts."""
    candidates = [
        getattr(settings, "FONTS_DIR", Path("/app/fonts")),
        Path("/app/fonts"),
        Path(__file__).resolve().parents[4] / "fonts",
        Path("/usr/share/fonts/truetype/khmeros"),
        Path("/usr/share/fonts/truetype/noto"),
    ]
    for candidate in candidates:
        if candidate and candidate.exists() and any(candidate.glob("*.ttf")):
            return candidate.resolve()
    return Path("/app/fonts")


def verify_subtitle_system_prerequisites(force: bool = False) -> bool:
    """Verify that FFmpeg, libass, HarfBuzz complex shaping, and Khmer fonts are installed.
    Fails loudly with a descriptive RuntimeError if any requirement is missing.
    """
    global _PREREQUISITES_VERIFIED
    if _PREREQUISITES_VERIFIED and not force:
        return True

    # 1. Verify FFmpeg binary
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        error_msg = (
            "FFmpeg executable not found on system PATH. "
            "Please install ffmpeg with libass and libharfbuzz support."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)

    # 2. Verify libass filter in FFmpeg
    try:
        res = subprocess.run(
            [ffmpeg_bin, "-filters"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        filters_stdout = res.stdout.lower()
        has_ass_filter = (
            " ass " in filters_stdout
            or "\tass\t" in filters_stdout
            or " ass" in filters_stdout
        )
        if not has_ass_filter:
            error_msg = (
                "FFmpeg is missing libass support ('ass' filter not found in `ffmpeg -filters`). "
                "Ensure ffmpeg is compiled with `--enable-libass`."
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg)
    except subprocess.SubprocessError as e:
        logger.error("Failed to inspect FFmpeg filters: %s", e)
        raise RuntimeError(f"Could not verify FFmpeg filter capabilities: {e}")

    # 3. Verify HarfBuzz complex shaping engine in libass
    fonts_dir = get_fonts_dir()
    with tempfile.NamedTemporaryFile("w", suffix=".ass", encoding="utf-8") as f:
        f.write(
            "[Script Info]\n"
            "ScriptType: v4.00+\n"
            "PlayResX: 64\n"
            "PlayResY: 64\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Khmer OS Battambang,20,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,គណិតវិទ្យា\n"
        )
        f.flush()

        probe_cmd = [
            ffmpeg_bin,
            "-f", "lavfi",
            "-i", "color=c=black:s=64x64:d=0.04",
            "-vf", f"ass={f.name}:fontsdir={fonts_dir}",
            "-f", "null",
            "-",
        ]
        try:
            probe_res = subprocess.run(
                probe_cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            output = probe_res.stderr + probe_res.stdout
            if "HarfBuzz" not in output:
                error_msg = (
                    "libass is built without HarfBuzz complex shaping support. "
                    "Khmer subscript consonants (coeng) and dependent vowels cannot be shaped correctly. "
                    "Rebuild or install ffmpeg with libharfbuzz enabled."
                )
                logger.critical(error_msg)
                raise RuntimeError(error_msg)
        except subprocess.SubprocessError as e:
            logger.error("Failed to run libass HarfBuzz probe: %s", e)
            raise RuntimeError(f"FFmpeg ASS filter execution failed during startup check: {e}")

    # 4. Verify Khmer font availability (fontconfig or bundled directory)
    available_fonts = set()
    try:
        fc_res = subprocess.run(
            ["fc-list", ":", "family"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if fc_res.returncode == 0:
            for line in fc_res.stdout.splitlines():
                for fam in line.split(","):
                    cleaned = fam.strip()
                    if cleaned:
                        available_fonts.add(cleaned)
    except Exception as e:
        logger.warning("Could not execute fc-list during font verification: %s", e)

    # Also check bundled fonts directory directly
    if fonts_dir.exists():
        bundled_map = {
            "KhmerOSbattambang.ttf": "Khmer OS Battambang",
            "KhmerOScontent.ttf": "Khmer OS Content",
            "KhmerOSmuol.ttf": "Khmer OS Muol",
            "NotoSansKhmer-Regular.ttf": "Noto Sans Khmer",
            "NotoSansKhmer-Bold.ttf": "Noto Sans Khmer",
        }
        for file_name, family_name in bundled_map.items():
            if (fonts_dir / file_name).exists():
                available_fonts.add(family_name)

    found_khmer_fonts = [f for f in REQUIRED_KHMER_FONTS if f in available_fonts]
    if not found_khmer_fonts:
        error_msg = (
            "No verified Khmer font found in fontconfig or bundled fontsdir. "
            "At least 'Khmer OS Battambang' or 'Noto Sans Khmer' must be installed to prevent broken glyphs."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)

    logger.info(
        "Subtitle system prerequisites verified: FFmpeg ass filter active with HarfBuzz complex shaping, fonts: %s",
        found_khmer_fonts,
    )
    _PREREQUISITES_VERIFIED = True
    return True
