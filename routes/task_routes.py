import os
import sys

# Force UTF-8 output on Windows to prevent UnicodeEncodeError from emoji in video titles
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Blueprint, request, jsonify
from pydantic import ValidationError
import json
import re
import urllib.parse

# Import Models & Services
from models.data_models import (
    TaskGenerateRequest, SearchResourcesRequest, AnalyzeConceptsRequest,
    TaskGenerateResponse, LearningResource
)
from services.intent_analyzer import intent_analyzer
from services.resource_fetcher import resource_fetcher
from services.relevance_scorer import relevance_scorer
from services.scheduler_service import scheduler_service
from cache.lightweight_cache import cache
from utils.concept_utils import purify_concept, split_concepts, categorize_resource_appropriately, parse_semantic_concepts

task_bp = Blueprint("task", __name__)

DEVANAGARI_RE = re.compile(r"[\u0900-\u097f]")


# =====================================================================
# HELPER UTILITIES
# =====================================================================

def extract_video_id(video_url: str) -> str:
    """Extract the 11-character YouTube video ID from any YouTube URL format."""
    video_url = (video_url or "").strip()
    regex = r"(?:youtube(?:-nocookie)?\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?|shorts|live)\/|.*[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})"
    match = re.search(regex, video_url)
    if match:
        return match.group(1)
    if len(video_url) == 11 and re.match(r"^[a-zA-Z0-9_-]{11}$", video_url):
        return video_url
    return video_url


def transliterate_to_hinglish(text: str) -> str:
    """
    If text contains Devanagari characters (Hindi script), transliterate to
    Roman script (Hinglish) instead of translating to English.
    Handles casual typing representation (e.g. 'fir hum ye dekhenge')
    and linguistic schwa-deletion with 0 external dependencies.
    """
    if not text or not DEVANAGARI_RE.search(text):
        return text

    # Vowels & Matras
    VOWELS = {
        '\u0905': 'a',   # अ
        '\u0906': 'a',   # आ
        '\u0907': 'i',   # इ
        '\u0908': 'i',   # ई
        '\u0909': 'u',   # उ
        '\u090a': 'u',   # ऊ
        '\u090b': 'ri',  # ऋ
        '\u090f': 'e',   # ए
        '\u0910': 'ai',  # ऐ
        '\u0913': 'o',   # ओ
        '\u0914': 'au',  # औ
        
        # Matras (vowel signs)
        '\u093e': 'a',   # ा
        '\u093f': 'i',   # ि
        '\u0940': 'i',   # ी
        '\u0941': 'u',   # ु
        '\u0942': 'u',   # ू
        '\u0943': 'ri',  # ृ
        '\u0947': 'e',   # े
        '\u0948': 'ai',  # ै
        '\u094b': 'o',   # ो
        '\u094c': 'au',  # ौ
        '\u0949': 'o',   # ॉ
        '\u0945': 'e',   # ॅ
    }

    # Consonants mapping
    CONSONANTS = {
        '\u0915': 'k',   # क
        '\u0916': 'kh',  # ख
        '\u0917': 'g',   # ग
        '\u0918': 'gh',  # घ
        '\u0919': 'n',   # ङ
        '\u091a': 'ch',  # च
        '\u091b': 'chh', # छ
        '\u091c': 'j',   # ज
        '\u091d': 'jh',  # झ
        '\u091e': 'n',   # ञ
        '\u091f': 't',   # ट
        '\u0920': 'th',  # ठ
        '\u0921': 'd',   # ड
        '\u0922': 'dh',  # ढ
        '\u0923': 'n',   # ण
        '\u0924': 't',   # त
        '\u0925': 'th',  # थ
        '\u0926': 'd',   # द
        '\u0927': 'dh',  # ध
        '\u0928': 'n',   # न
        '\u092a': 'p',   # प
        '\u092b': 'f',   # फ (mostly pronounced/written as 'f' in casual Hinglish)
        '\u092c': 'b',   # ब
        '\u092d': 'bh',  # भ
        '\u092e': 'm',   # म
        '\u092f': 'y',   # य
        '\u0930': 'r',   # र
        '\u0932': 'l',   # ल
        '\u0933': 'l',   # ळ
        '\u0935': 'v',   # व
        '\u0936': 'sh',  # श
        '\u0937': 'sh',  # ष
        '\u0938': 's',   # स
        '\u0939': 'h',   # ह
    }

    # Special modifiers
    MODIFIERS = {
        '\u0902': 'n',   # Anusvara (ं)
        '\u0901': 'n',   # Chandrabindu (ँ)
        '\u0903': 'h',   # Visarga (ः)
        '\u093c': '',    # Nukta (़)
    }

    tokens = re.split(r'(\s+|[^\u0900-\u097f\w]+)', text)
    words = []
    
    for token in tokens:
        if not token or not DEVANAGARI_RE.search(token):
            words.append(token)
            continue
            
        word_out = []
        i = 0
        n = len(token)
        
        while i < n:
            char = token[i]
            
            # Nukta combinations check
            if i + 1 < n and token[i+1] == '\u093c':
                combined = char + '\u093c'
                if combined == 'फ़':
                    word_out.append('f')
                elif combined == 'ज़':
                    word_out.append('z')
                elif combined == 'ड़':
                    word_out.append('r')
                elif combined == 'ढ़':
                    word_out.append('rh')
                elif combined == 'ख़':
                    word_out.append('kh')
                elif combined == 'ग़':
                    word_out.append('g')
                elif combined == 'क़':
                    word_out.append('q')
                else:
                    word_out.append(CONSONANTS.get(char, ''))
                i += 2
                continue
                
            # Consonant check
            if char in CONSONANTS:
                base_consonant = CONSONANTS[char]
                next_char = token[i+1] if i + 1 < n else None
                
                word_out.append(base_consonant)
                
                # Halant suppresses inherent 'a'
                if next_char == '\u094d':
                    i += 2
                    continue
                # Matra suppresses inherent 'a'
                elif next_char in VOWELS and next_char not in ('\u0905', '\u0906', '\u0907', '\u0908', '\u0909', '\u090a', '\u090b', '\u090f', '\u0910', '\u0913', '\u0914'):
                    i += 1
                    continue
                # Modifier
                elif next_char in MODIFIERS:
                    word_out.append('a')
                    i += 1
                    continue
                # End of word suppresses inherent 'a'
                elif next_char is None or next_char.isspace() or not DEVANAGARI_RE.match(next_char):
                    i += 1
                    continue
                else:
                    word_out.append('a')
                    i += 1
                    continue
                    
            # Vowel/matra check
            elif char in VOWELS:
                word_out.append(VOWELS[char])
                i += 1
                continue
                
            # Modifier check
            elif char in MODIFIERS:
                word_out.append(MODIFIERS[char])
                i += 1
                continue
                
            else:
                word_out.append(char)
                i += 1
                
        w = "".join(word_out).lower()
        
        # Apply linguistic schwa deletion (C1-a-C2-a-C3-V structures)
        w = re.sub(r'([b-df-hj-np-tv-z]+a[b-df-hj-np-tv-z]+)a([b-df-hj-np-tv-z]+[aeiou])', r'\1\2', w)
        
        # High-frequency dictionary overrides for standard casual Hinglish
        replacements = {
            'hama': 'hum',
            'hamare': 'humare',
            'phira': 'fir',
            'yaha': 'yeh',
            'vaha': 'woh',
            'hai': 'hai',
            'hain': 'hain',
            'tha': 'tha',
            'the': 'the',
            'thi': 'thi',
            'ki': 'ki',
            'ko': 'ko',
            'se': 'se',
            'aur': 'aur',
            'kara': 'kar',
            'para': 'par',
            'karke': 'karke',
            'raha': 'raha',
            'rahe': 'rahe',
            'rahi': 'rahi',
            'laga': 'laga',
            'lage': 'lage',
            'lagi': 'lagi',
            'chahiye': 'chahiye',
            'sath': 'saath',
            'bhi': 'bhi',
            'kuch': 'kuch',
            'bahut': 'bohot',
            'kyon': 'kyun',
            'kaise': 'kaise',
            'kya': 'kya',
            'kab': 'kab',
            'kahan': 'kahan',
            'idhar': 'idhar',
            'udhar': 'udhar',
            'apna': 'apna',
            'apne': 'apne',
            'apni': 'apni',
            'hota': 'hota',
            'hote': 'hote',
            'hoti': 'hoti',
            'hi': 'hi',
            'to': 'to',
            'karne': 'karne',
            'karna': 'karna',
            'dekhne': 'dekhne',
            'dekhna': 'dekhna',
            'samajh': 'samajh',
            'sikhna': 'sikhna',
            'sikhne': 'sikhne',
            'vidiyo': 'video',
        }
        
        if w in replacements:
            w = replacements[w]
            
        w = w.replace("shh", "sh")
        w = w.replace("chh", "ch")
        w = re.sub(r'o+', 'o', w)
        w = re.sub(r'e+', 'e', w)
        w = re.sub(r'i+', 'i', w)
        
        if w in ('hama', 'ham'):
            w = 'hum'
        elif w == 'phir':
            w = 'fir'
            
        words.append(w)
        
    return "".join(words)


def translate_if_hindi(text: str) -> str:
    """Legacy helper: translate Hindi Devanagari to English via Google Translate."""
    if not text:
        return text
    if re.search(r"[\u0900-\u097f]", text):
        try:
            from deep_translator import GoogleTranslator
            translated = GoogleTranslator(source="auto", target="en").translate(text)
            print(f"[AI Backend] Translated Hindi text to English: '{text[:40]}' -> '{translated[:40]}'")
            return translated
        except Exception as e:
            print(f"[AI Backend] Translation error: {e}")
    return text


def parse_description_to_segments(description: str, video_title: str = "Attached Video", video_duration: float = 0.0) -> list:
    if not description:
        return []

    lines = description.split('\n')
    timestamp_pattern = re.compile(r'\b(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\b')

    raw_segments = []

    for idx, line in enumerate(lines):
        line_stripped = line.strip()
        match = timestamp_pattern.search(line_stripped)
        if match:
            hours = int(match.group(1)) if match.group(1) else 0
            minutes = int(match.group(2))
            seconds = int(match.group(3))
            start_time = hours * 3600 + minutes * 60 + seconds

            span = match.span()
            clean_title = line_stripped[:span[0]] + line_stripped[span[1]:]
            clean_title = re.sub(r'^[ \t\-\:\(\)\[\]\.\,\=\u2013\u2014]+|[ \t\-\:\(\)\[\]\.\,\=\u2013\u2014]+$', '', clean_title).strip()

            if not clean_title:
                clean_title = f"Section at {match.group(0)}"

            raw_segments.append({
                "start": start_time,
                "title": clean_title,
                "line_idx": idx
            })

    if not raw_segments:
        return []

    raw_segments.sort(key=lambda x: x["start"])

    unique_raw = []
    seen_starts = set()
    for r in raw_segments:
        if r["start"] not in seen_starts:
            seen_starts.add(r["start"])
            unique_raw.append(r)

    final_segments = []
    num_segs = len(unique_raw)

    for i in range(num_segs):
        current = unique_raw[i]
        start = current["start"]
        title = current["title"]
        line_idx = current["line_idx"]

        next_line_idx = len(lines)
        if i + 1 < num_segs:
            next_line_idx = unique_raw[i + 1]["line_idx"]

        content_lines = []
        for l_idx in range(line_idx + 1, next_line_idx):
            l = lines[l_idx].strip()
            if l and not re.match(r'^[\-\=\*\_ \t\u2013\u2014]+$', l):
                l_lower = l.lower()
                if any(kw in l_lower for kw in ["http", "subscribe", "twitter", "instagram", "facebook", "patreon", "github"]):
                    continue
                content_lines.append(l)

        content_desc = " ".join(content_lines)
        content_desc = re.sub(r'\s+', ' ', content_desc).strip()

        duration = 60.0
        if i + 1 < num_segs:
            duration = float(unique_raw[i+1]["start"] - start)
        elif video_duration > start:
            duration = float(video_duration - start)

        if content_desc:
            text = f"Topic: {title}. {content_desc}"
        else:
            text = f"Topic: {title}. Learn about '{title}' in this section of the video '{video_title}'."

        final_segments.append({
            "text": text,
            "start": float(start),
            "duration": float(max(duration, 5.0))
        })

    return final_segments


def fetch_direct_transcript(video_url: str) -> dict | None:
    """
    Attempt to fetch official YouTube subtitles for a single video.
    Returns a transcript result dict or None on failure.
    """
    video_id = extract_video_id(video_url)
    cache_key = f"transcript_{video_id}"

    cached = cache.get(cache_key)
    if cached:
        print(f"[AI Backend] Cache hit for transcript: {video_id}")
        return cached

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript_list = YouTubeTranscriptApi().list(video_id)
        preferred_languages = ["en", "es", "fr", "de", "hi", "ja"]
        selected_transcript = None

        try:
            selected_transcript = transcript_list.find_transcript(preferred_languages)
        except Exception:
            try:
                selected_transcript = next(iter(transcript_list))
            except Exception:
                pass

        if not selected_transcript:
            return None

        # For Hindi transcripts: transliterate to Hinglish (keep as Roman-script Hindi)
        # For other non-English: translate to English
        lang_code = getattr(selected_transcript, 'language_code', 'en')
        is_hindi = lang_code in ('hi', 'bho', 'raj', 'mai', 'awa')

        if not is_hindi and lang_code != 'en':
            try:
                selected_transcript = selected_transcript.translate('en')
            except Exception as trans_err:
                print(f"[AI Backend] Could not auto-translate transcript ({lang_code}): {repr(trans_err)}")

        srt = selected_transcript.fetch()
        segments = []
        for snippet in srt:
            snippet_text = snippet['text'] if isinstance(snippet, dict) else getattr(snippet, 'text', str(snippet))
            # Apply Hinglish transliteration for Hindi content
            processed_text = transliterate_to_hinglish(snippet_text)
            segments.append({
                "text": processed_text,
                "start": snippet['start'] if isinstance(snippet, dict) else getattr(snippet, 'start', 0.0),
                "duration": snippet['duration'] if isinstance(snippet, dict) else getattr(snippet, 'duration', 0.0)
            })

        result = {
            "success": True,
            "transcript": {"segments": segments},
            "extractionMethod": "youtube-transcript-api"
        }
        cache.set(cache_key, result, ttl=604800)
        return result

    except Exception as e:
        print(f"[AI Backend] Direct subtitle fetch failed for {video_id}: {repr(e)}")
        return None


def fetch_video_metadata(video_id: str, provided_title: str = "Attached Video Learning Resource") -> dict:
    """Fetch video metadata (title, description, duration, chapters) via yt_dlp."""
    video_title = provided_title
    video_description = ""
    video_duration = 0.0
    chapters = []

    try:
        import yt_dlp
        ydl_opts = {
            'skip_download': True,
            'extract_flat': False,
            'quiet': True,
            'no_warnings': True,
            'no_color': True,
            'encoding': 'utf-8',
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            if info:
                video_title = info.get("title") or video_title
                video_description = info.get("description") or ""
                video_duration = float(info.get("duration") or 0.0)
                chapters = info.get("chapters") or []
                safe_title = video_title.encode('ascii', errors='replace').decode('ascii')
                print(f"[AI Backend] yt_dlp metadata: '{safe_title}', {video_duration}s, {len(chapters)} chapters")
    except Exception as ytdl_err:
        print(f"[AI Backend] yt_dlp metadata fetch error for {video_id}: {repr(ytdl_err).encode('ascii', errors='replace').decode('ascii')}")

    # Fallback title via noembed
    if video_title == provided_title:
        try:
            import requests as req_lib
            noembed_res = req_lib.get(f"https://noembed.com/embed?url=https://www.youtube.com/watch?v={video_id}", timeout=5)
            if noembed_res.ok:
                video_title = noembed_res.json().get("title") or video_title
        except Exception:
            pass

    return {
        "video_id": video_id,
        "title": video_title,
        "description": video_description,
        "duration": video_duration,
        "chapters": chapters
    }


def build_local_timeline_from_metadata(metadata: dict) -> list:
    """Build a local fallback transcript timeline from yt_dlp metadata."""
    video_title = metadata.get("title", "Attached Video")
    video_description = metadata.get("description", "")
    video_duration = metadata.get("duration", 0.0)
    chapters = metadata.get("chapters", [])
    fallback_segments = []

    if chapters:
        print(f"[AI Backend] Using {len(chapters)} native chapters for timeline.")
        for chap in chapters:
            start = chap.get("start_time", 0.0)
            end = chap.get("end_time", start + 30.0)
            chap_title = chap.get("title", "Topic").strip()
            duration = end - start
            fallback_segments.append({
                "text": f"Topic: {chap_title}. Study this segment to learn about '{chap_title}' in the video '{video_title}'.",
                "start": float(start),
                "duration": float(max(duration, 5.0))
            })
        return fallback_segments

    if video_description:
        parsed_segs = parse_description_to_segments(video_description, video_title, video_duration)
        if parsed_segs:
            print(f"[AI Backend] Parsed {len(parsed_segs)} timestamps from description.")
            return parsed_segs

        # Spread description paragraphs
        lines = [l.strip() for l in video_description.split('\n') if l.strip()]
        clean_lines = [l for l in lines if not any(kw in l.lower() for kw in ["http", "subscribe", "twitter", "instagram", "facebook", "patreon", "github"])]

        if clean_lines:
            chunks = []
            temp_chunk = []
            for l in clean_lines:
                temp_chunk.append(l)
                if len(temp_chunk) >= 2 or len(" ".join(temp_chunk)) >= 150:
                    chunks.append(" ".join(temp_chunk))
                    temp_chunk = []
            if temp_chunk:
                chunks.append(" ".join(temp_chunk))

            chunks = chunks[:12]
            if chunks:
                total_dur = video_duration if video_duration > 0 else 600.0
                seg_dur = total_dur / len(chunks)
                for idx, chunk in enumerate(chunks):
                    fallback_segments.append({
                        "text": f"Topic: Chapter {idx+1}. {chunk}",
                        "start": float(idx * seg_dur),
                        "duration": float(seg_dur)
                    })
                return fallback_segments

    # Generic 4-section timeline as absolute last resort
    print(f"[AI Backend] Generating generic 4-section timeline for: '{video_title}'")
    total_dur = video_duration if video_duration > 0 else 600.0
    sections = [
        ("Introduction and Overview", f"Introduction and foundational overview of the concepts presented in '{video_title}'."),
        ("Core Concepts and Fundamentals", f"Exploring the core principles, terminologies, and underlying mechanics of '{video_title}'."),
        ("Practical Applications & Deep Dive", f"Analyzing real-world examples, step-by-step walk-throughs, and demonstrations related to '{video_title}'."),
        ("Summary, Review, and Key Takeaways", f"Summarizing the lecture, discussing best practices, and highlighting major takeaways from '{video_title}'.")
    ]
    seg_dur = total_dur / len(sections)
    for idx, (sec_title, sec_desc) in enumerate(sections):
        fallback_segments.append({
            "text": f"Topic: {sec_title}. {sec_desc}",
            "start": float(idx * seg_dur),
            "duration": float(seg_dur)
        })

    return fallback_segments


def fetch_gemini_batch_timelines(batch_inputs: list, api_key: str) -> dict:
    """
    Send a SINGLE Gemini API call for multiple videos that need AI-generated timelines.
    Returns a dict mapping videoUrl -> transcript result dict.
    """
    import requests as req_lib
    import time

    if not batch_inputs or not api_key:
        return {}

    # Cap batch size at 8 to keep prompt manageable
    BATCH_SIZE = 8
    all_results = {}

    for chunk_start in range(0, len(batch_inputs), BATCH_SIZE):
        batch_chunk = batch_inputs[chunk_start:chunk_start + BATCH_SIZE]

        videos_summary = []
        for i, v in enumerate(batch_chunk):
            desc_snippet = (v.get("description") or "")[:500]
            chapters_list = v.get("chapters") or []
            chapters_str = ", ".join([c.get("title", "") for c in chapters_list[:5]]) if chapters_list else "none"
            duration_mins = int((v.get("duration") or 0) / 60)
            videos_summary.append(
                f'Video {i+1}:\n'
                f'  URL: {v["videoUrl"]}\n'
                f'  Title: {v["title"]}\n'
                f'  Duration: ~{duration_mins} minutes\n'
                f'  Chapters: {chapters_str}\n'
                f'  Description excerpt: {desc_snippet}'
            )

        videos_block = "\n\n".join(videos_summary)

        prompt = f"""You are an expert AI study assistant. The following {len(batch_chunk)} YouTube videos do not have official subtitles.
For EACH video, generate a structured learning timeline of 8-12 key topic segments with realistic timestamps.
Each segment must have an educational "text" field with the topic name and a brief learning summary, a "start" time in seconds, and a "duration" in seconds.

Videos to process:
{videos_block}

IMPORTANT: You MUST return valid JSON in exactly this format (one entry per video URL):
{{
  "results": {{
    "<videoUrl1>": {{
      "segments": [
        {{"text": "Topic: [Name]. [Educational summary]", "start": 0, "duration": 90}},
        ...
      ]
    }},
    "<videoUrl2>": {{
      "segments": [...]
    }}
  }}
}}

Do not include markdown formatting. Return only the raw JSON object."""

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"}
        }
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

        res = None
        for attempt in range(3):
            try:
                res = req_lib.post(gemini_url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
                if res.status_code == 429:
                    wait_time = 3 * (attempt + 1)
                    print(f"[AI Backend] Gemini batch rate limit (429). Retrying in {wait_time}s...", flush=True)
                    time.sleep(wait_time)
                else:
                    break
            except Exception as req_err:
                print(f"[AI Backend] Gemini batch request error: {repr(req_err)}")
                break

        if res and res.ok:
            try:
                text_response = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                if text_response.startswith("```json"):
                    text_response = text_response.split("```json", 1)[1]
                if text_response.endswith("```"):
                    text_response = text_response.rsplit("```", 1)[0]
                text_response = text_response.strip()
                parsed = json.loads(text_response)
                results = parsed.get("results", {})
                for item in batch_chunk:
                    video_url = item["videoUrl"]
                    video_data = results.get(video_url)
                    if video_data and video_data.get("segments"):
                        result = {
                            "success": True,
                            "transcript": {"segments": video_data["segments"]},
                            "extractionMethod": "gemini-ai-timeline-batch"
                        }
                        # Cache individual result
                        video_id = extract_video_id(video_url)
                        cache.set(f"transcript_{video_id}", result, ttl=604800)
                        all_results[video_url] = result
                        print(f"[AI Backend] Gemini batch: got {len(video_data['segments'])} segments for {video_id}")
            except Exception as parse_err:
                print(f"[AI Backend] Gemini batch parse error: {repr(parse_err)}")
        else:
            status = res.status_code if res else "no response"
            print(f"[AI Backend] Gemini batch call failed with status: {status}")

    return all_results


# =====================================================================
# AUTHORITATIVE RESOURCE HELPERS
# =====================================================================

AUTHORITATIVE_DOCS = {
    "react": { "title": "React Official Documentation", "url": "https://react.dev" },
    "python": { "title": "Python Standard Library Docs", "url": "https://docs.python.org/3/" },
    "javascript": { "title": "MDN Web Docs - JavaScript Reference", "url": "https://developer.mozilla.org/en-US/docs/Web/JavaScript" },
    "dsa": { "title": "GeeksforGeeks - Data Structures Catalog", "url": "https://www.geeksforgeeks.org/data-structures/" },
    "machine learning": { "title": "Scikit-Learn Machine Learning Docs", "url": "https://scikit-learn.org/stable/" },
    "langchain": { "title": "LangChain Agents & RAG Framework Reference", "url": "https://python.langchain.com/docs/get_started/introduction" },
    "sql": { "title": "W3Schools SQL Language Guide", "url": "https://www.w3schools.com/sql/" },
    "vector databases": { "title": "Pinecone Vector Database Learning Hub", "url": "https://www.pinecone.io/learn/" },
    "rag": { "title": "Hugging Face RAG Concept Guide", "url": "https://huggingface.co/docs/transformers/model_doc/rag" }
}

def get_authoritative_doc(concept_name: str) -> dict:
    clean_query = purify_concept(concept_name)
    normalized = clean_query.lower().strip()
    for key, match in AUTHORITATIVE_DOCS.items():
        if key in normalized:
            return {
                "title": match["title"],
                "url": match["url"],
                "type": "doc",
                "estimatedDuration": "2 hours",
                "sourcePlatform": match["title"].split()[0]
            }
    return {
        "title": f"{clean_query} Study Guide & Docs",
        "url": f"https://www.google.com/search?q={urllib.parse.quote(clean_query + ' official documentation study guide tutorial')}",
        "type": "doc",
        "estimatedDuration": "3 hours",
        "sourcePlatform": "Google Search"
    }

AUTHORITATIVE_PRACTICE = {
    "react": { "title": "StackBlitz React Sandbox Playground", "url": "https://stackblitz.com/edit/react" },
    "python": { "title": "HackerRank Python Practice Arena", "url": "https://www.hackerrank.com/domains/python" },
    "dsa": { "title": "LeetCode Dynamic Programming & DSA Prep", "url": "https://leetcode.com/studyplan/top-interview-150/" },
    "sql": { "title": "SQLBolt Interactive Practice Tutorials", "url": "https://sqlbolt.com/" },
    "machine learning": { "title": "Kaggle Machine Learning Competitions", "url": "https://www.kaggle.com/competitions" }
}

def get_authoritative_practice(concept_name: str) -> dict:
    clean_query = purify_concept(concept_name)
    normalized = clean_query.lower().strip()
    for key, match in AUTHORITATIVE_PRACTICE.items():
        if key in normalized:
            return {
                "title": match["title"],
                "url": match["url"],
                "type": "site",
                "estimatedDuration": "4 hours",
                "sourcePlatform": match["title"].split()[0]
            }
    return {
        "title": f"{clean_query} Concept Quiz & Exercises",
        "url": f"https://www.google.com/search?q={urllib.parse.quote(clean_query + ' test questions quiz practice problems mcq exercises')}",
        "type": "site",
        "estimatedDuration": "2.5 hours",
        "sourcePlatform": "Google Search"
    }


# =====================================================================
# TASK GENERATION ROUTE
# =====================================================================

@task_bp.route("/generate-task", methods=["POST"])
def generate_task():
    try:
        body = request.get_json() or {}
        req_data = TaskGenerateRequest(**body)
    except ValidationError as e:
        return jsonify({"success": False, "errors": e.errors()}), 400

    cache_key = f"gen_task_{req_data.concepts}_{req_data.duration}_{req_data.scheduleType}_{req_data.resourcePreference}_{getattr(req_data, 'enginePreference', 'hybrid')}"
    cached_val = cache.get(cache_key)
    if cached_val:
        print(f"\n=========================================\n[TASK GENERATION] CACHE HIT: Serving cached study roadmap for '{req_data.taskTitle}'\n=========================================\n", flush=True)
        return jsonify(cached_val), 200

    nlp_results = intent_analyzer.analyze(req_data.concepts)
    categories = nlp_results["categories"]
    difficulty = nlp_results["difficulty"]
    tags = nlp_results["tags"]
    harvested_resources = []

    task_words = [w.strip() for w in re.sub(r'[|\[\]()\-:.,!_]', ' ', req_data.taskTitle).split() if w.strip()]
    task_category_fallback = " ".join([w.capitalize() for w in task_words[:3]]) if task_words else "Learning Resource"
    primary_category = categories[0] if (categories and categories[0] != "General Learning") else task_category_fallback

    playlists_raw = []
    videos_raw = []
    docs_raw = []
    practice_raw = []
    roadmaps_raw = []

    raw_search = req_data.concepts if req_data.concepts and req_data.concepts.strip() else req_data.taskTitle
    semantic_concepts = parse_semantic_concepts(raw_search)

    print(f"Executing NLP Semantic Resource Crawling for: '{req_data.taskTitle}' with {len(semantic_concepts)} concept(s)")

    for sc in semantic_concepts:
        query_base = sc["final_query"]
        if req_data.resourcePreference == "playlist":
            crawler_query = f"{query_base} playlist"
            playlists_raw.extend(resource_fetcher.crawl_youtube_playlists(crawler_query, limit=3))
        elif req_data.resourcePreference == "video":
            crawler_query = f"{query_base} one shot"
            videos_raw.extend(resource_fetcher.crawl_youtube_videos(crawler_query, limit=3))
        else:
            crawler_query_playlist = f"{query_base} playlist"
            crawler_query_video = f"{query_base} one shot"
            playlists_raw.extend(resource_fetcher.crawl_youtube_playlists(crawler_query_playlist, limit=2))
            videos_raw.extend(resource_fetcher.crawl_youtube_videos(crawler_query_video, limit=2))

    for sc in semantic_concepts:
        query_base = sc["final_query"]
        docs_raw.append(get_authoritative_doc(query_base))
        practice_raw.append(get_authoritative_practice(query_base))

    primary_query = semantic_concepts[0]["final_query"] if semantic_concepts else raw_search
    roadmaps_raw.extend(resource_fetcher.crawl_duckduckgo(f"{primary_query} roadmap", site_filter="roadmap.sh", limit=2))
    if not roadmaps_raw and primary_category == "JEE Prep":
        roadmaps_raw.extend(resource_fetcher.crawl_duckduckgo(f"{primary_query} syllabus guide", limit=2))

    candidates = playlists_raw + videos_raw + docs_raw + roadmaps_raw + practice_raw

    target_difficulty = req_data.skillLevel or difficulty
    for item in candidates:
        item["category"] = categorize_resource_appropriately(
            item.get("title", ""),
            item.get("url", ""),
            req_data.concepts,
            item.get("type", "")
        )
        item["difficulty"] = target_difficulty

    seen_urls = set()
    deduped_candidates = []
    for c in candidates:
        url = c["url"]
        if url not in seen_urls:
            seen_urls.add(url)
            deduped_candidates.append(c)

    api_key = getattr(req_data, "geminiApiKey", None) or request.headers.get("X-Gemini-Key") or os.getenv("GEMINI_API_KEY")
    use_gemini_success = False
    engine_pref = getattr(req_data, "enginePreference", "hybrid")

    if engine_pref == "crawl":
        print(f"[AI Backend] Engine preference is 'crawl'. Skipping Gemini curation completely.", flush=True)
    elif engine_pref == "gemini" and not api_key:
        print(f"[AI Backend] Forced Gemini curation but no Gemini API key is configured.", flush=True)
        return jsonify({
            "success": False,
            "error": "No Gemini API key is configured. Please provide one in the UI Curation Engine settings or in backend .env file."
        }), 400
    elif api_key:
        print(f"[AI Backend] Invoking Gemini API to curate resources and construct premium learning roadmap for: '{req_data.taskTitle}'...")
        try:
            import requests
            import json as json_lib

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}

            candidates_formatted = []
            for i, c in enumerate(deduped_candidates[:25]):
                candidates_formatted.append({
                    "id": i,
                    "title": c.get("title", ""),
                    "url": c.get("url", ""),
                    "type": c.get("type", "video"),
                    "sourcePlatform": c.get("sourcePlatform", "")
                })

            prompt = f"""
            You are an expert educational curriculum builder and study assistant.
            The user wants to learn about: "{req_data.concepts}"
            Their target task title is: "{req_data.taskTitle}"
            Their overall study duration is: "{req_data.duration}"
            Their milestone schedule type is: "{req_data.scheduleType}" (either "daily" or "weekly" intervals)
            Their skill level is: "{req_data.skillLevel or 'intermediate'}"
            Their resource preference is: "{req_data.resourcePreference or 'mixed'}" (options: "playlist", "video" (one-shots), or "mixed")

            We have crawled the following pool of real, live candidate study resources (real URLs & titles):
            {json_lib.dumps(candidates_formatted, indent=2)}

            Please perform the following steps:
            1. Curate and select the BEST 5 to 10 resources from the candidate pool that are highly relevant to the concepts.
               - Prioritize the user's resource preference (e.g. if playlist, favor playlists; if video, favor one-shots; if mixed, select a balance of both).
               - Ensure you include high-quality documentation, websites, or roadmaps as well!
               - If the candidate pool is sparse or lacks high-quality docs/practice sites, you can supplement them with highly authoritative, well-known educational websites or guides (e.g., freeCodeCamp, MDN Web Docs, Khan Academy, GeeksforGeeks, W3Schools, roadmap.sh) with real, working domain URLs.
            2. For each curated resource:
               - Write a premium, clear educational title.
               - Set a realistic "estimatedDuration" (e.g., "45 minutes", "2.5 hours", "6 hours").
               - Assign an appropriate "category" (e.g., "Video Series", "Interactive Roadmap", "Documentation", "Hands-on Practice").
               - Give it an "aiScore" out of 100 based on quality and relevance.
               - Assign 2 to 4 relevant educational "tags" (e.g., ["React", "State Management", "Tutorial"]).
               - Keep the exact "url", "type", and "sourcePlatform" from the pool if selected (or use valid standard URLs if supplemented).
            3. Build a sequential learning timeline/schedule ("suggestedPlan") matching the user's duration and scheduleType:
               - If scheduleType is "daily", map out the specific days (e.g., "Day 1", "Day 2", etc.) up to 7-10 days depending on duration.
               - If scheduleType is "weekly", map out the specific weeks (e.g., "Week 1", "Week 2", etc.) up to the full duration weeks.
               - For each period (Day/Week), assign a specific list of sub-topics to cover, and a list of step-by-step "tasks" to complete.
               - Explicitly reference the titles of the curated resources in the tasks so the user knows which resource to study for that milestone!

            You MUST return your response as a valid JSON object matching this schema:
            {{
              "categories": ["Category 1", "Category 2"],
              "resources": [
                {{
                  "title": "Clear Resource Title",
                  "url": "https://...",
                  "type": "playlist" | "video" | "doc" | "pdf" | "site" | "roadmap",
                  "category": "Video Series" | "Documentation" | "Practice Portals" | "Roadmaps",
                  "estimatedDuration": "3 hours",
                  "thumbnail": "",
                  "sourcePlatform": "YouTube" | "MDN Web Docs" | "roadmap.sh" | etc,
                  "difficulty": "{req_data.skillLevel or 'intermediate'}",
                  "aiScore": 95,
                  "tags": ["tag1", "tag2"]
                }}
              ],
              "suggestedPlan": [
                {{
                  "period": "Week 1" or "Day 1",
                  "topics": ["Sub-topic A", "Sub-topic B"],
                  "tasks": ["Watch playlist 'Resource Title' to master sub-topic A", "Read the docs at 'Doc Resource Title'", "Complete practical exercise"]
                }}
              ]
            }}

            Do not add any markdown formatting (like ```json), just return the raw JSON object string.
            """

            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"}
            }

            import time
            res = None
            for attempt in range(3):
                res = requests.post(url, json=payload, headers=headers, timeout=20)
                if res.status_code == 429:
                    wait_time = 2 * (attempt + 1)
                    print(f"[AI Backend] Gemini API returned status 429 (Rate Limit). Retrying in {wait_time} seconds...", flush=True)
                    time.sleep(wait_time)
                else:
                    break

            if res and res.ok:
                text_response = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                if text_response.startswith("```json"):
                    text_response = text_response.split("```json", 1)[1]
                if text_response.endswith("```"):
                    text_response = text_response.rsplit("```", 1)[0]
                text_response = text_response.strip()

                parsed_data = json_lib.loads(text_response)

                curated_resources = parsed_data.get("resources", [])
                for r in curated_resources:
                    if not r.get("thumbnail"):
                        if r.get("type") in ["playlist", "video"]:
                            r["thumbnail"] = "https://images.unsplash.com/photo-1611162617213-7d7a39e9b1d7?w=120&auto=format&fit=crop"
                        else:
                            r["thumbnail"] = "https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?w=120&auto=format&fit=crop"

                response_data = {
                    "success": True,
                    "engine": "gemini",
                    "task": {
                        "title": req_data.taskTitle,
                        "duration": req_data.duration,
                        "scheduleType": req_data.scheduleType
                    },
                    "categories": parsed_data.get("categories", categories),
                    "resources": curated_resources,
                    "suggestedPlan": parsed_data.get("suggestedPlan", [])
                }

                print(f"\n=========================================\n[TASK GENERATION] ACTIVE ENGINE: Gemini AI Curation\nSuccessfully generated premium study roadmap for '{req_data.taskTitle}'\n=========================================\n", flush=True)
                use_gemini_success = True

                cache.set(cache_key, response_data)
                return jsonify(response_data), 200
            else:
                print(f"[AI Backend] Gemini AI resource curation returned status: {res.status_code}. Falling back to manual relevance scorer...")
                if engine_pref == "gemini":
                    return jsonify({
                        "success": False,
                        "error": f"Gemini API returned status {res.status_code}: {res.text}"
                    }), 502
        except Exception as err:
            print(f"[AI Backend] Failed to run Gemini resource curation: {repr(err)}. Falling back to manual relevance scorer...")
            if engine_pref == "gemini":
                return jsonify({
                    "success": False,
                    "error": f"Failed to run Gemini AI Curation: {repr(err)}"
                }), 500

    # ======================================================
    # FALLBACK PATH (Robust Jaro-Winkler Scorer & Scheduler)
    # ======================================================
    print(f"\n=========================================\n[TASK GENERATION] ACTIVE ENGINE: Crawl + Relevance Scorer (Fallback)\nRunning manual relevance-ranking pipeline for '{req_data.taskTitle}'\n=========================================\n", flush=True)

    scored_resources = relevance_scorer.filter_and_score(deduped_candidates, req_data.concepts, primary_category)
    harvested_resources.extend(scored_resources)

    suggested_plan = scheduler_service.build_plan(
        title=req_data.taskTitle,
        categories=categories,
        resources=harvested_resources,
        duration=req_data.duration,
        schedule_type=req_data.scheduleType
    )

    response_data = {
        "success": True,
        "engine": "crawl_fallback",
        "task": {
            "title": req_data.taskTitle,
            "duration": req_data.duration,
            "scheduleType": req_data.scheduleType
        },
        "categories": categories,
        "resources": harvested_resources,
        "suggestedPlan": suggested_plan
    }

    cache.set(cache_key, response_data)
    return jsonify(response_data), 200


# =====================================================================
# SEARCH RESOURCES ROUTE
# =====================================================================

@task_bp.route("/search-resources", methods=["POST"])
def search_resources():
    try:
        body = request.get_json() or {}
        req_data = SearchResourcesRequest(**body)
    except ValidationError as e:
        return jsonify({"success": False, "errors": e.errors()}), 400

    cache_key = f"search_res_{req_data.query}_{req_data.searchType}_{req_data.limit}"
    cached_val = cache.get(cache_key)
    if cached_val:
        return jsonify(cached_val), 200

    playlists = resource_fetcher.crawl_youtube_playlists(req_data.query, limit=req_data.limit)
    videos = resource_fetcher.crawl_youtube_videos(req_data.query, limit=req_data.limit)
    docs = resource_fetcher.crawl_duckduckgo(req_data.query, limit=req_data.limit)

    merged = playlists + videos + docs

    seen_urls = set()
    deduped = []
    for m in merged:
        if m["url"] not in seen_urls:
            seen_urls.add(m["url"])
            deduped.append(m)

    scored = relevance_scorer.filter_and_score(deduped, req_data.query, "General Search")

    response_data = {
        "success": True,
        "query": req_data.query,
        "resources": scored[:req_data.limit]
    }

    cache.set(cache_key, response_data)
    return jsonify(response_data), 200


# =====================================================================
# ANALYZE CONCEPTS ROUTE
# =====================================================================

@task_bp.route("/analyze-concepts", methods=["POST"])
def analyze_concepts():
    try:
        body = request.get_json() or {}
        req_data = AnalyzeConceptsRequest(**body)
    except ValidationError as e:
        return jsonify({"success": False, "errors": e.errors()}), 400

    nlp_results = intent_analyzer.analyze(req_data.text)

    return jsonify({
        "success": True,
        "analysis": nlp_results
    }), 200


# =====================================================================
# SINGLE VIDEO TRANSCRIPT ROUTE
# =====================================================================

@task_bp.route("/transcript", methods=["POST"])
def get_video_transcript():
    try:
        body = request.get_json() or {}
        video_url = body.get("url", "").strip()
        if not video_url:
            return jsonify({"success": False, "message": "Missing 'url' parameter"}), 400

        video_id = extract_video_id(video_url)
        print(f"[AI Backend] Fetching transcript for video_id: {video_id}")

        # 1. Check Cache first
        cache_key = f"transcript_{video_id}"
        cached_res = cache.get(cache_key)
        if cached_res is not None:
            print(f"[AI Backend] Serving cached transcript for video_id: {video_id}")
            return jsonify(cached_res), 200

        # 2. Try direct subtitle fetch
        direct_result = fetch_direct_transcript(video_url)
        if direct_result:
            return jsonify(direct_result), 200

        # 3. Fetch metadata via yt_dlp
        metadata = fetch_video_metadata(video_id, "Attached Video Learning Resource")
        video_title = metadata["title"]
        video_description = metadata["description"]

        # 4. Try Gemini AI fallback for topic timeline
        api_key = body.get("geminiApiKey") or request.headers.get("X-Gemini-Key") or os.getenv("GEMINI_API_KEY")
        if api_key:
            print(f"[AI Backend] Running Gemini AI fallback for: '{video_title}'...")
            try:
                import requests as req_lib
                import time

                desc_context = f"\nVideo Description:\n{video_description[:1000]}" if video_description else ""
                gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
                prompt = f"""You are an expert AI study assistant. The user wants to learn from a YouTube video titled "{video_title}" (ID: {video_id}).{desc_context}
However, the official subtitles/transcripts for this video are missing or disabled.

Please generate a highly realistic, highly structured learning timeline/roadmap of 8 to 15 key topics, concepts, and keywords covered in this video.
For each concept, estimate a start time (in seconds, starting at 0 and spaced logically across a typical video timeline of e.g. 0 to 20 minutes) and a duration.
For each concept, write a clear, highly educational study block that contains the core keywords and a concise description of what is learned.

You MUST return your response as a valid JSON object matching this schema:
{{
  "segments": [
    {{
      "text": "Topic: [Concept Name]. Learn about [Keywords/Concepts]. [Detailed summary of the topic's content]",
      "start": <start_time_in_seconds_float_or_int>,
      "duration": <duration_in_seconds_float_or_int>
    }}
  ]
}}

Do not add any markdown formatting (like ```json), just return the raw JSON object string."""

                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"}
                }

                res = None
                for attempt in range(3):
                    res = req_lib.post(gemini_url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
                    if res.status_code == 429:
                        wait_time = 2 * (attempt + 1)
                        print(f"[AI Backend] Gemini transcript fallback rate limit. Retrying in {wait_time}s...", flush=True)
                        time.sleep(wait_time)
                    else:
                        break

                if res and res.ok:
                    text_response = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if text_response.startswith("```json"):
                        text_response = text_response.split("```json", 1)[1]
                    if text_response.endswith("```"):
                        text_response = text_response.rsplit("```", 1)[0]
                    text_response = text_response.strip()
                    parsed = json.loads(text_response)
                    gemini_segments = parsed.get("segments")
                    if gemini_segments:
                        gemini_result = {
                            "success": True,
                            "transcript": {"segments": gemini_segments},
                            "extractionMethod": "gemini-ai-timeline"
                        }
                        print(f"\n=========================================\n[TRANSCRIPT EXTRACTION] ACTIVE ENGINE: Gemini AI\nGenerated topic timeline for video ID: {video_id}\n=========================================\n", flush=True)
                        cache.set(cache_key, gemini_result, ttl=604800)
                        return jsonify(gemini_result), 200
                else:
                    print(f"[AI Backend] Gemini API call failed with status: {res.status_code if res else 'No Response'}.")
            except Exception as gemini_err:
                print(f"[AI Backend] Gemini AI fallback error: {repr(gemini_err)}")
        else:
            print(f"[AI Backend] No Gemini API key. Using local yt_dlp fallback...")

        # 5. Local keyless fallback (chapters/description/generic)
        fallback_segments = build_local_timeline_from_metadata(metadata)
        if fallback_segments:
            fallback_result = {
                "success": True,
                "transcript": {"segments": fallback_segments},
                "extractionMethod": "ytdl-chapters-fallback"
            }
            print(f"\n=========================================\n[TRANSCRIPT EXTRACTION] ACTIVE ENGINE: yt_dlp Local Fallback\nGenerated timeline for video ID: {video_id}\n=========================================\n", flush=True)
            cache.set(cache_key, fallback_result, ttl=604800)
            return jsonify(fallback_result), 200

        # 6. DuckDuckGo web search fallback
        print(f"[AI Backend] Crawling DuckDuckGo for topic: '{video_title}'")
        web_results = resource_fetcher.crawl_duckduckgo(video_title, limit=3)
        segments = []
        start_time = 0.0
        for item in web_results:
            snippet = item.get("snippet", "").strip()
            t = item.get("title", "").strip()
            u = item.get("url", "").strip()
            if snippet:
                segments.append({
                    "text": f"Study Topic: {t}. {snippet} [Reference: {u}]",
                    "start": start_time,
                    "duration": 15.0
                })
                start_time += 15.0

        if not segments:
            segments = [{
                "text": f"Welcome to the interactive learning deck for the video '{video_title}'. "
                        f"There are no official transcripts for this resource. "
                        f"You can add your own notes, bookmarks, and study questions during playback.",
                "start": 0.0,
                "duration": 10.0
            }]

        final_fallback = {
            "success": True,
            "transcript": {"segments": segments},
            "extractionMethod": "web-tutorial-fallback"
        }
        cache.set(cache_key, final_fallback, ttl=604800)
        return jsonify(final_fallback), 200

    except Exception as e:
        print(f"[AI Backend] Critical error fetching transcript: {repr(e)}")
        return jsonify({
            "success": True,
            "message": str(e),
            "transcript": {
                "segments": [{
                    "text": "Topic: Video Overview. A study timeline is being prepared for this video resource.",
                    "start": 0.0,
                    "duration": 10.0
                }]
            },
            "extractionMethod": "web-tutorial-fallback"
        }), 200


# =====================================================================
# BATCH VIDEO TRANSCRIPT ROUTE (NEW - production optimized)
# =====================================================================

@task_bp.route("/transcript/batch", methods=["POST"])
def get_video_transcripts_batch():
    """
    Process multiple videos in a single request.
    - Fetches YouTube subtitles for all videos in parallel threads (Tier 1)
    - Fetches yt_dlp metadata for failures in parallel (Tier 2)
    - Sends all failures to Gemini in ONE API call (Tier 3 - batch)
    - Falls back to local timeline generation per-video (Tier 4)
    Always returns HTTP 200 with per-video results. Never exposes errors to user.
    """
    try:
        body = request.get_json() or {}
        items = body.get("items") or body.get("videos") or []
        if not isinstance(items, list) or len(items) == 0:
            return jsonify({"success": False, "message": "Missing 'items' parameter"}), 400

        api_key = body.get("geminiApiKey") or request.headers.get("X-Gemini-Key") or os.getenv("GEMINI_API_KEY")

        normalized_items = []
        for item in items:
            video_url = (item.get("url") or item.get("videoUrl") or "").strip()
            if not video_url:
                continue
            normalized_items.append({
                "url": video_url,
                "title": item.get("title") or "Attached Video Learning Resource"
            })

        if not normalized_items:
            return jsonify({"success": False, "message": "No valid video URLs supplied"}), 400

        resolved_results: dict = {}
        subtitle_misses = []

        # Tier 1: Parallel subtitle fetching for all videos
        with ThreadPoolExecutor(max_workers=min(6, max(2, len(normalized_items)))) as executor:
            future_map = {
                executor.submit(fetch_direct_transcript, item["url"]): item
                for item in normalized_items
            }
            for future in as_completed(future_map):
                item = future_map[future]
                try:
                    result = future.result()
                except Exception as err:
                    print(f"[AI Backend] Subtitle fetch failed for {item['url']}: {repr(err)}")
                    result = None

                if result:
                    resolved_results[item["url"]] = result
                else:
                    subtitle_misses.append(item)

        # Tier 2: Parallel metadata fetching for subtitle failures
        metadata_by_url = {}
        if subtitle_misses:
            with ThreadPoolExecutor(max_workers=min(6, max(2, len(subtitle_misses)))) as executor:
                future_map = {
                    executor.submit(fetch_video_metadata, extract_video_id(item["url"]), item["title"]): item
                    for item in subtitle_misses
                }
                for future in as_completed(future_map):
                    item = future_map[future]
                    try:
                        metadata_by_url[item["url"]] = future.result()
                    except Exception as err:
                        print(f"[AI Backend] Metadata fetch failed for {item['url']}: {repr(err)}")
                        metadata_by_url[item["url"]] = {
                            "video_id": extract_video_id(item["url"]),
                            "title": item["title"],
                            "description": "",
                            "duration": 0.0,
                            "chapters": []
                        }

        # Tier 3: yt_dlp local timeline for remaining failures (NO Gemini in batch — preserves API quota)
        # The frontend will apply client-side NLP on top of this metadata for smarter results.
        remaining = [item for item in normalized_items if item["url"] not in resolved_results]
        if remaining:
            for item in remaining:
                try:
                    metadata = metadata_by_url.get(item["url"])
                    if not metadata:
                        metadata = fetch_video_metadata(extract_video_id(item["url"]), item["title"])

                    fallback_segments = build_local_timeline_from_metadata(metadata)
                    video_title_for_client = (metadata or {}).get("title") or item["title"]
                    video_duration_for_client = (metadata or {}).get("duration") or 0.0
                except Exception as err:
                    print(f"[AI Backend] Local fallback failed for {item['url']}: {repr(err).encode('ascii', errors='replace').decode('ascii')}")
                    fallback_segments = []
                    video_title_for_client = item["title"]
                    video_duration_for_client = 0.0

                fallback_result = {
                    "success": True,
                    "transcript": {"segments": fallback_segments},
                    # Signal frontend to apply client-side NLP smart timeline
                    "extractionMethod": "ytdl-chapters-fallback",
                    "needsClientNLP": len(fallback_segments) <= 4,  # generic 4-section = frontend should enrich
                    "videoTitle": video_title_for_client,
                    "videoDuration": video_duration_for_client,
                }
                resolved_results[item["url"]] = fallback_result

        # Build ordered results matching input order
        ordered_results = []
        for item in normalized_items:
            result = resolved_results.get(item["url"])
            if result:
                ordered_results.append({
                    "videoUrl": item["url"],
                    "title": item["title"],
                    **result
                })

        print(f"\n=========================================\n[TRANSCRIPT BATCH] Processed {len(ordered_results)}/{len(normalized_items)} videos\n=========================================\n", flush=True)

        return jsonify({
            "success": True,
            "results": ordered_results
        }), 200

    except Exception as e:
        print(f"[AI Backend] Critical error fetching transcript batch: {repr(e)}")
        return jsonify({"success": True, "results": []}), 200


# =====================================================================
# OCR SERVER ROUTE
# =====================================================================

@task_bp.route("/ocr-server", methods=["POST"])
def ocr_server_fallback():
    try:
        import os
        import tempfile
        import requests

        body = request.get_json() or {}
        pdf_url = body.get("url", "").strip()
        if not pdf_url:
            return jsonify({"success": False, "message": "Missing 'url' parameter"}), 400

        print(f"[AI Backend] Running server-side OCR fallback for url: {pdf_url}")

        fd, temp_pdf = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)

        try:
            res = requests.get(pdf_url, timeout=30)
            if not res.ok:
                return jsonify({"success": False, "message": f"Failed to download PDF from {pdf_url}"}), 400
            with open(temp_pdf, "wb") as f:
                f.write(res.content)

            pages_text = []
            try:
                import pypdf
                reader = pypdf.PdfReader(temp_pdf)
                for i, page in enumerate(reader.pages):
                    text = page.extract_text() or ""
                    pages_text.append({
                        "page": i + 1,
                        "text": text.strip(),
                        "confidence": 95 if text.strip() else 0
                    })
            except Exception as read_err:
                print(f"[AI Backend] Native PDF reader failed: {read_err}")

            return jsonify({
                "success": True,
                "pages": pages_text,
                "extractionMethod": "server-ocr-fallback"
            }), 200
        finally:
            if os.path.exists(temp_pdf):
                try:
                    os.remove(temp_pdf)
                except Exception:
                    pass
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# =====================================================================
# LIGHTWEIGHT INTELLIGENT SEARCH & INGESTION SYSTEM ROUTES
# =====================================================================
import requests
from rapidfuzz import process, fuzz

def classify_query(query: str):
    query_lower = query.lower().strip()

    resource_type = "mixed"
    if any(kw in query_lower for kw in ["playlist", "course playlist", "lectures", "series"]):
        resource_type = "playlist"
    elif any(kw in query_lower for kw in ["one shot", "oneshot", "video", "tutorial", "crash course"]):
        resource_type = "video"
    elif any(kw in query_lower for kw in ["pdf", "notes", "book", "sheets", "handout"]):
        resource_type = "pdf"
    elif any(kw in query_lower for kw in ["docs", "documentation", "reference", "api", "guide"]):
        resource_type = "docs"
    elif any(kw in query_lower for kw in ["roadmap", "curriculum", "path"]):
        resource_type = "roadmap"
    elif any(kw in query_lower for kw in ["website", "blog", "article", "portal"]):
        resource_type = "website"

    stop_words = [
        "playlist", "playlists", "one shot", "oneshot", "video", "videos",
        "tutorial", "tutorials", "crash course", "course", "courses",
        "series", "lectures", "pdf", "notes", "book", "books", "sheets",
        "docs", "documentation", "guide", "guides", "reference", "api",
        "roadmap", "roadmaps", "curriculum", "path", "best", "for beginners",
        "complete", "interview", "videos", "crash", "notes", "questions",
        "practice", "sheet"
    ]

    topic = query_lower
    for sw in stop_words:
        topic = re.sub(rf'\b{re.escape(sw)}\b', '', topic)

    topic = re.sub(r'\s+', ' ', topic).strip()
    if not topic:
        topic = query.strip()

    topic_capitalized = " ".join(word.capitalize() if word.lower() not in ["and", "or", "of", "in", "for", "to", "with", "a", "an", "the"] else word.lower() for word in topic.split())
    aliases = {
        "dsa": "DSA", "ml": "Machine Learning", "dl": "Deep Learning",
        "ai": "Artificial Intelligence", "os": "Operating Systems", "db": "Database",
        "dbms": "Database Management Systems", "sql": "SQL", "js": "JavaScript",
        "ts": "TypeScript", "html": "HTML", "css": "CSS", "oop": "OOP", "oops": "OOPs"
    }
    words = []
    for w in topic_capitalized.split():
        wl = w.lower()
        if wl in aliases:
            words.append(aliases[wl])
        else:
            words.append(w)
    topic_capitalized = " ".join(words)

    category_mappings = {
        "dsa": "Data Structures & Algorithms", "data structures": "Data Structures & Algorithms",
        "algorithms": "Data Structures & Algorithms", "machine learning": "Machine Learning",
        "deep learning": "Machine Learning", "neural network": "Machine Learning",
        "ai": "Machine Learning", "artificial intelligence": "Machine Learning",
        "operating system": "Operating Systems", "operating systems": "Operating Systems",
        "os": "Operating Systems", "react": "React & Frontend Development",
        "nextjs": "React & Frontend Development", "frontend": "React & Frontend Development",
        "javascript": "React & Frontend Development", "typescript": "React & Frontend Development",
        "html": "React & Frontend Development", "css": "React & Frontend Development",
        "tailwind": "React & Frontend Development", "vue": "React & Frontend Development",
        "angular": "React & Frontend Development", "backend": "Backend Development",
        "node": "Backend Development", "express": "Backend Development",
        "django": "Backend Development", "flask": "Backend Development",
        "spring": "Backend Development", "springboot": "Backend Development",
        "system design": "System Design", "system design interview": "System Design",
        "architecture": "System Design", "db": "Database Systems",
        "database": "Database Systems", "databases": "Database Systems",
        "sql": "Database Systems", "postgresql": "Database Systems",
        "mysql": "Database Systems", "mongodb": "Database Systems",
        "redis": "Database Systems", "devops": "DevOps & Cloud",
        "cloud": "DevOps & Cloud", "docker": "DevOps & Cloud",
        "kubernetes": "DevOps & Cloud", "aws": "DevOps & Cloud",
        "git": "DevOps & Cloud", "github": "DevOps & Cloud",
        "python": "Programming Languages", "java": "Programming Languages",
        "c++": "Programming Languages", "cpp": "Programming Languages",
        "golang": "Programming Languages", "rust": "Programming Languages"
    }

    matched_category = None
    for key, cat in category_mappings.items():
        if key in topic.lower():
            matched_category = cat
            break

    if not matched_category:
        best_match = process.extractOne(topic, list(category_mappings.keys()), scorer=fuzz.partial_ratio)
        if best_match and best_match[1] > 75:
            matched_category = category_mappings[best_match[0]]
        else:
            matched_category = topic_capitalized

    enhanced = query.strip()
    if resource_type == "playlist":
        enhanced = f"best {topic_capitalized} complete course playlist"
    elif resource_type == "video":
        enhanced = f"{topic_capitalized} one shot tutorial complete course"
    elif resource_type == "pdf":
        enhanced = f"{topic_capitalized} hand-written notes pdf free download"
    elif resource_type == "docs":
        enhanced = f"{topic_capitalized} official documentation developer guide reference"
    elif resource_type == "roadmap":
        enhanced = f"{topic_capitalized} curriculum visual learning roadmap sh"
    elif resource_type == "website":
        enhanced = f"{topic_capitalized} complete tutorial guide blog article"

    return {
        "topic": topic_capitalized,
        "resource_type": resource_type,
        "enhanced_query": enhanced,
        "category": matched_category
    }


@task_bp.route("/classify-resource", methods=["POST"])
def classify_resource():
    try:
        body = request.get_json() or {}
        query = body.get("query", "").strip()
        if not query:
            return jsonify({"success": False, "message": "Missing 'query' parameter"}), 400

        classification = classify_query(query)
        return jsonify({
            "success": True,
            **classification
        }), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@task_bp.route("/search", methods=["POST"])
def search_resources_ingest():
    try:
        body = request.get_json() or {}
        query = body.get("query", "").strip()
        limit = int(body.get("limit", 5))
        if not query:
            return jsonify({"success": False, "message": "Missing 'query' parameter"}), 400

        classification = classify_query(query)
        r_type = classification["resource_type"]
        enhanced_query = classification["enhanced_query"]
        category = classification["category"]

        playlists_raw = []
        videos_raw = []
        docs_raw = []

        if r_type == "playlist":
            playlists_raw.extend(resource_fetcher.crawl_youtube_playlists(enhanced_query, limit=limit))
        elif r_type == "video":
            videos_raw.extend(resource_fetcher.crawl_youtube_videos(enhanced_query, limit=limit))
        elif r_type == "pdf":
            docs_raw.extend(resource_fetcher.crawl_duckduckgo(enhanced_query, limit=limit))
        elif r_type in ["docs", "website"]:
            docs_raw.extend(resource_fetcher.crawl_duckduckgo(enhanced_query, limit=limit))
        elif r_type == "roadmap":
            docs_raw.extend(resource_fetcher.crawl_duckduckgo(enhanced_query, site_filter="roadmap.sh", limit=limit))
        else:
            playlists_raw.extend(resource_fetcher.crawl_youtube_playlists(f"{classification['topic']} playlist", limit=3))
            videos_raw.extend(resource_fetcher.crawl_youtube_videos(f"{classification['topic']} one shot", limit=3))
            docs_raw.extend(resource_fetcher.crawl_duckduckgo(classification['topic'], limit=3))

        candidates = []

        for item in playlists_raw:
            candidates.append({
                "title": item.get("title", "Untitled Playlist"),
                "url": item["url"],
                "type": "playlist",
                "sourcePlatform": "YouTube",
                "thumbnail": item.get("thumbnail"),
                "channelName": item.get("channelName", "YouTube Channel"),
                "duration": item.get("estimatedDuration", "Complete Course"),
                "category": category
            })

        for item in videos_raw:
            title_lower = item.get("title", "").lower()
            if any(spam in title_lower for spam in ["music", "song", "movie", "trailer", "gaming", "highlights", "stream", "dance"]):
                continue
            candidates.append({
                "title": item.get("title", "Untitled Video"),
                "url": item["url"],
                "type": "video",
                "sourcePlatform": "YouTube",
                "thumbnail": item.get("thumbnail"),
                "channelName": item.get("channelName", "YouTube Channel"),
                "duration": item.get("estimatedDuration", "Video"),
                "category": category
            })

        for item in docs_raw:
            url = item["url"]
            domain = url.split("//")[-1].split("/")[0]
            platform_name = "Web Resource"
            if "geeksforgeeks.org" in domain:
                platform_name = "GeeksforGeeks"
            elif "developer.mozilla.org" in domain:
                platform_name = "Mozilla Developer Network"
            elif "roadmap.sh" in domain:
                platform_name = "roadmap.sh"
            elif "tutorialspoint.com" in domain:
                platform_name = "TutorialsPoint"
            elif "github.com" in domain:
                platform_name = "GitHub"
            elif "w3schools.com" in domain:
                platform_name = "W3Schools"

            res_type = "docs"
            if ".pdf" in url.lower() or "pdf" in item.get("title", "").lower() or r_type == "pdf":
                res_type = "pdf"
            elif "roadmap" in url.lower() or "roadmap" in item.get("title", "").lower() or r_type == "roadmap":
                res_type = "roadmap"

            candidates.append({
                "title": item.get("title", "Reference Docs"),
                "url": url,
                "type": res_type,
                "sourcePlatform": platform_name,
                "thumbnail": None,
                "channelName": domain,
                "duration": "Study Resource",
                "category": category
            })

        seen_urls = set()
        deduped_candidates = []
        for c in candidates:
            if c["url"] not in seen_urls:
                seen_urls.add(c["url"])
                deduped_candidates.append(c)

        return jsonify({
            "success": True,
            "category": category,
            "resource_type": r_type,
            "results": deduped_candidates[:limit*2]
        }), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@task_bp.route("/scrape", methods=["POST"])
def scrape_playlist():
    try:
        body = request.get_json() or {}
        playlist_url = body.get("url", "").strip()
        if not playlist_url:
            return jsonify({"success": False, "message": "Missing 'url' parameter"}), 400

        print(f"Scraping playlist URL: {playlist_url}")

        try:
            render_url = "https://my-back-si9a.onrender.com/extract"
            res = requests.post(render_url, json={"playlistUrl": playlist_url}, timeout=20)
            if res.ok:
                data = res.json()
                videos = data.get("videos", [])
                if videos:
                    return jsonify({
                        "success": True,
                        "videos": videos
                    }), 200
        except Exception as render_err:
            print(f"Render extract proxy fallback triggered: {render_err}")

        return jsonify({
            "success": False,
            "message": "Failed to scrape playlist videos. Please ensure it is a public playlist URL or try importing another resource."
        }), 500
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@task_bp.route("/transcribe-audio", methods=["POST"])
def transcribe_audio():
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file part in the request"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "message": "No selected file"}), 400

        print(f"[AI Backend] Received audio file for transcription: {file.filename}, content-type: {file.content_type}")

        import tempfile
        import os

        temp_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scratch")
        os.makedirs(temp_dir, exist_ok=True)

        suffix = os.path.splitext(file.filename)[1] or ".wav"
        temp_input_path = tempfile.mktemp(suffix=suffix, dir=temp_dir)
        file.save(temp_input_path)

        temp_wav_path = tempfile.mktemp(suffix=".wav", dir=temp_dir)

        import speech_recognition as sr
        r = sr.Recognizer()

        transcription_text = ""
        success = False
        error_msg = ""

        try:
            from pydub import AudioSegment
            try:
                print(f"[AI Backend] Converting {temp_input_path} to standard WAV via pydub...")
                audio = AudioSegment.from_file(temp_input_path)
                audio.export(temp_wav_path, format="wav")
                wav_file_to_use = temp_wav_path
            except Exception as pydub_err:
                print(f"[AI Backend] pydub conversion failed: {pydub_err}")
                if suffix.lower() == ".wav" or "wav" in (file.content_type or "").lower():
                    print("[AI Backend] File is already WAV. Using input file directly.")
                    wav_file_to_use = temp_input_path
                else:
                    raise Exception(f"Audio conversion error: {str(pydub_err)}. Please upload a .wav file.")

            with sr.AudioFile(wav_file_to_use) as source:
                print("[AI Backend] Recording audio source...")
                audio_data = r.record(source)

                print("[AI Backend] Running Google Web Speech Recognition in Hindi (hi-IN)...")
                try:
                    hindi_text = r.recognize_google(audio_data, language="hi-IN")
                    if re.search(r"[\u0900-\u097f]", hindi_text):
                        print(f"[AI Backend] Spoken Hindi detected: {hindi_text}")
                        # Use Hinglish transliteration for audio transcription too
                        transcription_text = transliterate_to_hinglish(hindi_text)
                        if transcription_text == hindi_text:
                            # Fallback to translation if transliteration not available
                            try:
                                from deep_translator import GoogleTranslator
                                transcription_text = GoogleTranslator(source="auto", target="en").translate(hindi_text)
                            except Exception:
                                pass
                        success = True
                        print(f"[AI Backend] Hinglish output: '{transcription_text}'")
                except Exception as hindi_err:
                    print(f"[AI Backend] Hindi speech recognition attempt passed/skipped: {hindi_err}")

                if not success:
                    print("[AI Backend] Running Google Web Speech Recognition in English (en-US)...")
                    try:
                        transcription_text = r.recognize_google(audio_data, language="en-US")
                        success = True
                    except Exception as eng_err:
                        print(f"[AI Backend] English (en-US) recognition failed: {eng_err}. Trying Indian English (en-IN)...")
                        try:
                            transcription_text = r.recognize_google(audio_data, language="en-IN")
                            success = True
                        except Exception as final_err:
                            raise final_err

                print(f"[AI Backend] Final transcription: {transcription_text[:100]}...")

        except sr.UnknownValueError:
            error_msg = "Google Speech Recognition could not understand the audio. Please speak more clearly."
            print(f"[AI Backend] Google Speech Recognition UnknownValueError: {error_msg}")
        except sr.RequestError as req_err:
            error_msg = f"Could not request results from Google Speech Recognition service; {req_err}"
            print(f"[AI Backend] Google Speech Recognition RequestError: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            print(f"[AI Backend] Transcription processing exception: {error_msg}")
        finally:
            for path in [temp_input_path, temp_wav_path]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception as cleanup_err:
                        print(f"[AI Backend] Temp file cleanup error for {path}: {cleanup_err}")

        if success:
            return jsonify({
                "success": True,
                "text": transcription_text
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": error_msg or "Failed to transcribe audio."
            }), 200

    except Exception as e:
        print(f"[AI Backend] Critical error inside transcribe_audio: {e}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500
