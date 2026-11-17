"""Emotion and acting style catalog and prosody configuration for Khmer speech synthesis and dubbing.

Provides presets for emotional tones (Angry, Sad, Happy, Whisper, Dramatic TVB, Storytelling, Explain, etc.)
with Microsoft Edge TTS prosody parameters (rate, pitch, volume) and translation prompt guidelines.
"""

from typing import Any, Dict, List, Optional, Tuple

EMOTION_STYLES: Dict[str, Dict[str, Any]] = {
    "calm": {
        "id": "calm",
        "label_km": "ធម្មតា / សុភាព",
        "label_en": "Neutral / Calm",
        "category": "general",
        "icon": "volume-2",
        "description": "Standard natural conversational tone. Balanced pitch and pacing for everyday dialogue.",
        "prosody": {
            "rate": "+0%",
            "pitch": "+0Hz",
            "volume": "+0%",
        },
        "translation_guidance": (
            "Translate in a natural, balanced, and conversational spoken Khmer tone. "
            "Use clear, authentic everyday spoken syntax."
        ),
    },
    "storytelling": {
        "id": "storytelling",
        "label_km": "និទានរឿង / ព្រេងនិទាន",
        "label_en": "Storytelling / Narration",
        "category": "narration",
        "icon": "book-open",
        "description": "Warm, measured, expressive storytelling cadence. Perfect for folktales, audiobooks, and history narratives.",
        "prosody": {
            "rate": "-10%",
            "pitch": "-2Hz",
            "volume": "+5%",
        },
        "translation_guidance": (
            "EMOTION & ACTING STYLE: និទានរឿង / ព្រេងនិទាន (Storytelling / Folk tale narration). "
            "Use evocative Cambodian narrative markers and transitional phrases (e.g. កាលពីព្រេងនាយ, ស្រាប់តែ, ដំណើររឿងមានដំណាលថា). "
            "Maintain smooth rhythmic sentence flow and poetic cadence suited for oral storytelling."
        ),
    },
    "explain": {
        "id": "explain",
        "label_km": "ពន្យល់ / អធិប្បាយ / បង្រៀន",
        "label_en": "Explaining / Tutorial",
        "category": "educational",
        "icon": "lightbulb",
        "description": "Articulate, steady, and clear pedagogical tone. Ideal for software tutorials, educational videos, and explainers.",
        "prosody": {
            "rate": "+0%",
            "pitch": "+2Hz",
            "volume": "+10%",
        },
        "translation_guidance": (
            "EMOTION & ACTING STYLE: ពន្យល់ / អធិប្បាយ (Explaining / Tutorial / Teaching). "
            "Use clear, didactic, and accessible Khmer phrasing (e.g. សូមមើលទាំងអស់គ្នា, ដូចដែលយើងបានដឹង, ជំហានបន្ទាប់គឺ). "
            "Prioritize step-by-step clarity, keeping technical terminology clear and precise."
        ),
    },
    "angry": {
        "id": "angry",
        "label_km": "ខឹងសម្បារ / ស្រែកប្រយុទ្ធ",
        "label_en": "Angry / Shouting / Combat",
        "category": "drama",
        "icon": "flame",
        "description": "Sharp, aggressive, loud, and intense. Suitable for action scenes, fight choreography, confrontations, and arguments.",
        "prosody": {
            "rate": "+15%",
            "pitch": "+15Hz",
            "volume": "+30%",
        },
        "translation_guidance": (
            "EMOTION & ACTING STYLE: ខឹងសម្បារ / ស្រែកប្រយុទ្ធ (Angry / Confrontational / Combat). "
            "Use fierce, emphatic, and aggressive spoken Khmer syntax. Incorporate sharp exclamatory particles "
            "(e.g. វ៉ើយ, ឯង, ឈប់ភ្លាម!, យ៉ាងម៉េច!). Sentences should feel punchy, urgent, and emotionally tense."
        ),
    },
    "happy": {
        "id": "happy",
        "label_km": "រីករាយ / សប្បាយរីករាយ",
        "label_en": "Happy / Cheerful / Joyful",
        "category": "emotion",
        "icon": "smile",
        "description": "Upbeat, energetic, and bright inflection. Fits celebrations, comedy, victory moments, and lighthearted vlogs.",
        "prosody": {
            "rate": "+10%",
            "pitch": "+15Hz",
            "volume": "+15%",
        },
        "translation_guidance": (
            "EMOTION & ACTING STYLE: រីករាយ / សប្បាយរីករាយ (Happy / Cheerful / Enthusiastic). "
            "Use lively, bright, and cheerful Khmer spoken expressions and joyful particles (e.g. ហាហា, សប្បាយណាស់, ណា៎, ពិតជាអស្ចារ្យ). "
            "Keep the phrasing warm, optimistic, and uplifting."
        ),
    },
    "sad": {
        "id": "sad",
        "label_km": "សោកសៅ / ខ្សឹកខ្សួល",
        "label_en": "Sad / Heartbroken / Mournful",
        "category": "emotion",
        "icon": "frown",
        "description": "Slow, lower pitch, subdued and melancholic. Great for tragic scenes, farewells, heartbreak, and emotional climaxes.",
        "prosody": {
            "rate": "-18%",
            "pitch": "-10Hz",
            "volume": "-20%",
        },
        "translation_guidance": (
            "EMOTION & ACTING STYLE: សោកសៅ / ខ្សឹកខ្សួល (Sad / Mournful / Heartbroken). "
            "Use gentle, sorrowful, and melancholic spoken Khmer phrasing. Incorporate poignant emotional markers "
            "(e.g. ហេតុអ្វីទៅ..., ឱ!..., ហាក់ដូចជា..., ទឹកភ្នែក). Pacing should feel slow, heavy, and grief-stricken."
        ),
    },
    "dramatic_tvb": {
        "id": "dramatic_tvb",
        "label_km": "តួឯកកុន / TVB Drama",
        "label_en": "Hero Dramatic / TVB Drama",
        "category": "drama",
        "icon": "clapperboard",
        "description": "High-stakes heroic Cambodian dubbing style as popularized in classic TVB series and Hong Kong cinema.",
        "prosody": {
            "rate": "+8%",
            "pitch": "+8Hz",
            "volume": "+25%",
        },
        "translation_guidance": (
            "EMOTION & ACTING STYLE: តួឯកកុន / TVB Drama (Heroic Theatrical Dubbing). "
            "Emulate the classic, vibrant Cambodian film dubbing style (របៀបបញ្ចូលសំឡេងកុនហុងកុង TVB). "
            "Use heroic, resolute, and theatrical expressions (e.g. មិនអាចទៅរួចទេ!, ថ្ងៃនេះជាថ្ងៃស្លាប់របស់ឯង!, លោកបង/អ្នកមីង). "
            "Keep dialogue dramatic, bold, and theatrical."
        ),
    },
    "whisper": {
        "id": "whisper",
        "label_km": "ខ្សឹប / អាថ៌កំបាំង",
        "label_en": "Whisper / Secret / Suspense",
        "category": "suspense",
        "icon": "mic-off",
        "description": "Hushed volume, intimate and covert pacing. Ideal for secrets, stealth missions, conspiracies, and horror suspense.",
        "prosody": {
            "rate": "-12%",
            "pitch": "-6Hz",
            "volume": "-35%",
        },
        "translation_guidance": (
            "EMOTION & ACTING STYLE: ខ្សឹប / អាថ៌កំបាំង (Hushed Whisper / Suspense / Stealth). "
            "Use intimate, secretive, and hushed Cambodian phrasing (e.g. ស្ងាត់ៗ..., កុំឱ្យគេដឹង..., ឆាប់មកនេះ...). "
            "Avoid loud particles or drawn-out exclamations; sentences should feel suppressed and cautious."
        ),
    },
    "excited": {
        "id": "excited",
        "label_km": "រំភើបញាប់ញ័រ",
        "label_en": "Excited / Thrilled / Hype",
        "category": "emotion",
        "icon": "zap",
        "description": "Rapid tempo and high pitch. Perfect for sports commentary, gaming hype, breaking news, and thrilling moments.",
        "prosody": {
            "rate": "+20%",
            "pitch": "+20Hz",
            "volume": "+25%",
        },
        "translation_guidance": (
            "EMOTION & ACTING STYLE: រំភើបញាប់ញ័រ (Thrilled / High Hype / Excited). "
            "Use punchy, fast-paced, and electrifying Khmer expressions (e.g. អស្ចារ្យខ្លាំងណាស់!, មើលទៅនោះ!, ពិតជាមិនគួរឱ្យជឿ!). "
            "Keep syntax concise and rapidly deliverable."
        ),
    },
    "fearful": {
        "id": "fearful",
        "label_km": "ភ័យខ្លាច / តក់ស្លុត",
        "label_en": "Fearful / Panic / Horror",
        "category": "suspense",
        "icon": "ghost",
        "description": "Tense and breathy with elevated pitch. Suited for horror films, suspenseful encounters, panic, and shock.",
        "prosody": {
            "rate": "+12%",
            "pitch": "+14Hz",
            "volume": "-5%",
        },
        "translation_guidance": (
            "EMOTION & ACTING STYLE: ភ័យខ្លាច / តក់ស្លុត (Fearful / Panicked / Horror). "
            "Use hurried, trembling, and anxious Khmer phrasing (e.g. ជួយផង!, មានរឿងអ្វីកើតឡើងហ្នឹង...!, ទៅឆ្ងាយទៅ!). "
            "Sentences should convey sudden dread, panic, and breathless tension."
        ),
    },
    "romantic": {
        "id": "romantic",
        "label_km": "ផ្អែមល្ហែម / ស្នេហា",
        "label_en": "Romantic / Sweet Love",
        "category": "drama",
        "icon": "heart",
        "description": "Soft, melodic, tender, and warm. Designed for romantic Korean/Thai dramas, love confessions, and intimate scenes.",
        "prosody": {
            "rate": "-8%",
            "pitch": "+4Hz",
            "volume": "-10%",
        },
        "translation_guidance": (
            "EMOTION & ACTING STYLE: ផ្អែមល្ហែម / ស្នេហា (Romantic / Sweet Affection). "
            "Use affectionate, gentle, and tender Cambodian pronouns and honorifics (e.g. បង, អូន, សម្លាញ់ចិត្ត, ស្រឡាញ់). "
            "Pacing should feel warm, tender, and deeply emotional."
        ),
    },
    "humorous": {
        "id": "humorous",
        "label_km": "កំប្លែង / លេងសើច",
        "label_en": "Humorous / Comedy / Playful",
        "category": "emotion",
        "icon": "laugh",
        "description": "Playful cadence and bouncy inflection. Perfect for sitcoms, comedic banter, parody, and jokes.",
        "prosody": {
            "rate": "+10%",
            "pitch": "+10Hz",
            "volume": "+15%",
        },
        "translation_guidance": (
            "EMOTION & ACTING STYLE: កំប្លែង / លេងសើច (Humorous / Comedy / Playful Banter). "
            "Use witty Cambodian colloquial banter, humorous colloquialisms, and playful exclamations (e.g. ចុមយក្ស, ហាសហា, អាហ្នឹងហើយ!). "
            "Keep the phrasing punchy, witty, and lighthearted."
        ),
    },
    "documentary": {
        "id": "documentary",
        "label_km": "ភាពយន្តឯកសារ",
        "label_en": "Documentary / Deep Narration",
        "category": "narration",
        "icon": "film",
        "description": "Authoritative, resonant, and measured. Ideal for National Geographic / BBC style nature and history documentaries.",
        "prosody": {
            "rate": "-12%",
            "pitch": "-10Hz",
            "volume": "+10%",
        },
        "translation_guidance": (
            "EMOTION & ACTING STYLE: ភាពយន្តឯកសារ (Documentary / Solemn Narration). "
            "Use polished, sophisticated, and dignified Khmer terminology suitable for documentary voiceovers. "
            "Maintain measured, intellectual cadence with gravitas."
        ),
    },
    "news": {
        "id": "news",
        "label_km": "ព័ត៌មានទូរទស្សន៍",
        "label_en": "News Broadcast / Anchor",
        "category": "educational",
        "icon": "radio",
        "description": "Crisp, formal, articulate, and steady. Tailored for news bulletins, corporate announcements, and formal broadcasts.",
        "prosody": {
            "rate": "+8%",
            "pitch": "+3Hz",
            "volume": "+15%",
        },
        "translation_guidance": (
            "EMOTION & ACTING STYLE: ព័ត៌មានទូរទស្សន៍ (News Broadcast / Anchor). "
            "Use formal, objective, and grammatically polished broadcasting Khmer (e.g. នាងខ្ញុំ/ខ្ញុំបាទសូមជម្រាបជូន...). "
            "Deliver information clearly, crisply, and authoritatively."
        ),
    },
}

DEFAULT_EMOTION_STYLE = "calm"


def list_emotion_styles() -> List[Dict[str, Any]]:
    """Return all available emotion and acting styles sorted for presentation."""
    return [dict(v) for v in EMOTION_STYLES.values()]


def get_emotion_style(style_id: Optional[str]) -> Dict[str, Any]:
    """Retrieve an emotion style by ID, falling back to 'calm'."""
    if not style_id:
        return dict(EMOTION_STYLES[DEFAULT_EMOTION_STYLE])
    sid = str(style_id).strip().lower()
    # Normalize aliases
    if sid in ("natural", "default", "neutral", "normal"):
        sid = "calm"
    elif sid in ("drama", "tvb", "hero"):
        sid = "dramatic_tvb"
    elif sid in ("story", "narration", "tale"):
        sid = "storytelling"
    elif sid in ("tutorial", "teaching", "education"):
        sid = "explain"
    elif sid in ("comedy", "joke"):
        sid = "humorous"

    return dict(EMOTION_STYLES.get(sid, EMOTION_STYLES[DEFAULT_EMOTION_STYLE]))


def resolve_prosody(
    emotion_style: Optional[str] = None,
    rate: Optional[Any] = None,
    pitch: Optional[Any] = None,
    volume: Optional[Any] = None,
    rate_factor: Optional[float] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Resolve final rate, pitch, and volume parameters.

    Explicit parameters override the style presets. If neither is specified,
    returns standard defaults.
    """
    style_info = get_emotion_style(emotion_style)
    prosody_preset = style_info.get("prosody", {})

    # 1. Rate resolution
    rate_str: Optional[str] = None
    if rate is not None:
        r = str(rate).strip()
        if not r.endswith("%"):
            r = f"{r}%"
        if not r.startswith(("+", "-")):
            r = f"+{r}"
        rate_str = r
    elif rate_factor is not None:
        pct = int(round((float(rate_factor) - 1.0) * 100))
        rate_str = f"+{pct}%" if pct >= 0 else f"{pct}%"
    else:
        rate_str = prosody_preset.get("rate")

    # 2. Pitch resolution
    pitch_str: Optional[str] = None
    if pitch is not None:
        p = str(pitch).strip()
        if not p.endswith(("Hz", "%", "st")):
            p = f"{p}Hz"
        if not p.startswith(("+", "-")):
            p = f"+{p}"
        pitch_str = p
    else:
        pitch_str = prosody_preset.get("pitch")

    # 3. Volume resolution
    volume_str: Optional[str] = None
    if volume is not None:
        v = str(volume).strip()
        if not v.endswith("%"):
            v = f"{v}%"
        if not v.startswith(("+", "-")):
            v = f"+{v}"
        volume_str = v
    else:
        volume_str = prosody_preset.get("volume")

    return rate_str, pitch_str, volume_str
