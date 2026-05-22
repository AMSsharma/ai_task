import re
from typing import List

# ======================================================
# ACRONYMS & ABBREVIATIONS (TO FORCE UPPERCASE)
# ======================================================
ACRONYMS = {
    "sql", "dbms", "dsa", "ml", "dl", "rag", "ai", "jwt", "html", "css", 
    "js", "ts", "pdf", "jee", "iit", "oop", "api", "rest", "orm", "mvc", 
    "dom", "cdn", "ux", "ui", "ci", "cd", "gk", "ssc", "cgl", "os"
}

def purify_concept(concept: str) -> str:
    """
    Cleans trailing channel/brand noise, languages, years, noise study terms, 
    special punctuation, and applies proper title/acronym capitalization.
    """
    if not concept:
        return ""
    clean = concept.strip()
    
    # 1. Strip trailing brand/channel qualifiers like "by [Channel]"
    clean = re.sub(r'\bby\s+.+$', '', clean, flags=re.IGNORECASE)
    
    # 2. Strip language specifiers
    clean = re.sub(r'\bin\s+(hindi|english|telugu|tamil|urdu|bengali|spanish|french|german)\b.*', '', clean, flags=re.IGNORECASE)
    
    # 3. Strip years
    clean = re.sub(r'\b(202\d)\b', '', clean)
    
    # 4. Strip standard study, lecture, and tutorial noise phrases
    noise_patterns = [
        r'\b(tutorial|course|playlist|video|videos|one\s*shot|oneshot|lecture|lectures|crash\s*course|learning\s*path|roadmap)\b',
        r'\b(complete|comprehensive|full|master|masterclass|basics?|foundations?|advanced?|practical)\b',
        r'\b(with\s+projects?|for\s+beginners?|for\s+placement|for\s+job)\b'
    ]
    for pattern in noise_patterns:
        clean = re.sub(pattern, '', clean, flags=re.IGNORECASE)
        
    # 5. Clean punctuation and excess spacing
    clean = re.sub(r'[.!?:()",]', '', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    
    if not clean:
        return ""
        
    # 6. Apply intelligent Title Case / Acronym Capitalization
    capitalized_words = []
    for w in clean.split():
        w_lower = w.lower()
        if w_lower in ACRONYMS:
            capitalized_words.append(w.upper())
        else:
            capitalized_words.append(w.capitalize())
            
    return " ".join(capitalized_words)

def parse_semantic_concepts(text: str) -> List[dict]:
    """
    Parses complex concept sentences with shared trailing modifier propagation.
    Example:
    'rajasthan gk and aptitude for ssc cgl'
    -> [
         {"base_concept": "Rajasthan GK", "shared_context": "for ssc cgl", "final_query": "Rajasthan GK SSC CGL"},
         {"base_concept": "Aptitude", "shared_context": "for ssc cgl", "final_query": "Aptitude For SSC CGL"}
       ]
    """
    if not text:
        return []
        
    # 1. Split the text by common conjunctions
    pattern = re.compile(r',|\+|\&|\band\b|\bwith\b', re.IGNORECASE)
    parts = [p.strip() for p in pattern.split(text) if p.strip()]
    
    if not parts:
        return []
        
    prep_pattern = re.compile(r'\b(for|to|in|on|with|at|by|of|from)\b', re.IGNORECASE)
        
    if len(parts) == 1:
        # Single concept: try splitting on prepositions
        raw_val = parts[0]
        match = prep_pattern.search(raw_val)
        if match:
            idx = match.start()
            base = raw_val[:idx].strip()
            context = raw_val[idx:].strip()
            prep_word = match.group(0)
            context_stripped = raw_val[idx + len(prep_word):].strip()
            return [{
                "base_concept": purify_concept(base),
                "shared_context": context,
                "final_query": f"{purify_concept(base)} {purify_concept(context_stripped)}"
            }]
        else:
            return [{
                "base_concept": purify_concept(raw_val),
                "shared_context": "",
                "final_query": purify_concept(raw_val)
            }]
            
    # Multi-concept case: len(parts) > 1
    base_parts = parts[:-1]
    last_part = parts[-1]
    
    # Identify shared modifier from last_part
    last_concept = last_part
    shared_context = ""
    shared_context_stripped = ""
    
    # Check for prepositions first (Case A)
    match = prep_pattern.search(last_part)
    
    if match:
        idx = match.start()
        last_concept = last_part[:idx].strip()
        shared_context = last_part[idx:].strip()
        prep_word = match.group(0)
        shared_context_stripped = last_part[idx + len(prep_word):].strip()
    else:
        # Check for word parallelism (Case B)
        # Take the first base part's word count
        first_base = base_parts[0]
        word_count = len(first_base.split())
        
        last_words = last_part.split()
        # Require a difference of at least 2 words to suggest a shared modifier,
        # preventing multi-word concepts (like 'linear algebra') from being split.
        if len(last_words) - word_count >= 2:
            last_concept = " ".join(last_words[:word_count])
            shared_context = " ".join(last_words[word_count:])
            shared_context_stripped = shared_context
            
    # Clean up and reconstruct
    purified_context = purify_concept(shared_context_stripped)
    results = []
    
    # Process base concepts
    for base in base_parts:
        purified_base = purify_concept(base)
        if purified_context:
            final_query = f"{purified_base} {purified_context}"
        else:
            final_query = purified_base
            
        results.append({
            "base_concept": purified_base,
            "shared_context": shared_context,
            "final_query": final_query
        })
        
    # Process the last concept
    # Keep the raw preposition phrase for the last concept to match "Aptitude For SSC CGL" perfectly!
    purified_last_base = purify_concept(last_concept)
    if shared_context:
        # If preposition was present, keep it in the final query (e.g. "Aptitude For SSC CGL")
        if prep_pattern.search(shared_context):
            raw_title = f"{purified_last_base} {shared_context.title()}"
            # Ensure acronym uppercase formatting in preposition phrase
            words = raw_title.split()
            capitalized = []
            for w in words:
                w_lower = w.lower()
                if w_lower in ACRONYMS:
                    capitalized.append(w.upper())
                else:
                    capitalized.append(w.capitalize())
            final_query = " ".join(capitalized)
        else:
            final_query = f"{purified_last_base} {purify_concept(shared_context)}"
    else:
        final_query = purified_last_base
        
    results.append({
        "base_concept": purified_last_base,
        "shared_context": shared_context,
        "final_query": final_query
    })
    
    return results

def split_concepts(text: str) -> List[str]:
    """
    Backward-compatible concept splitter.
    Extracts base concepts using the NLP-driven parse_semantic_concepts engine.
    """
    semantic = parse_semantic_concepts(text)
    return [sc["base_concept"] for sc in semantic]

def extract_playlist_category(title: str) -> str:
    """
    Extracts the first 2-4 meaningful words from a playlist title.
    Cleans out special characters and respects acronyms.
    """
    if not title:
        return "Playlist Curriculum"
        
    # Clean special separators
    clean = re.sub(r'[|\[\]()\-:.,!_]', ' ', title)
    words = [w.strip() for w in clean.split() if w.strip()]
    if not words:
        return "Playlist Curriculum"
        
    # Take first 2-4 words (limit to 3 if the 4th word is standard noise)
    limit = 3
    if len(words) >= 4:
        fourth_word = words[3].lower()
        if fourth_word in ["full", "course", "playlist", "videos", "video", "tutorial", "lectures", "lecture"]:
            limit = 3
        else:
            limit = 4
            
    # Capitalize acronyms correctly
    capitalized_words = []
    for w in words[:limit]:
        w_lower = w.lower()
        if w_lower in ACRONYMS:
            capitalized_words.append(w.upper())
        else:
            capitalized_words.append(w.capitalize())
            
    return " ".join(capitalized_words)

def categorize_resource_appropriately(title: str, url: str, concepts_str: str, resource_type: str) -> str:
    """
    The unified categorization engine.
    - Playlists: Named after title metadata.
    - Single Videos: Grouped under their matching semantic concept final query.
    - Docs/PDFs/Roadmaps: Named deterministically as '{final_query} Docs'.
    - Practice/Sites/Playgrounds: Named deterministically as '{final_query} Practice'.
    """
    # 1. Parse unique concepts using the semantic parser
    semantic_concepts = parse_semantic_concepts(concepts_str)
    if not semantic_concepts:
        return "General"
        
    first_concept = semantic_concepts[0]["final_query"]
    r_type = (resource_type or "").lower().strip()
    
    # 2. Playlist Logic: Meta-driven
    if r_type == "playlist":
        return extract_playlist_category(title)
        
    # 3. Concept matching logic for other resource types
    matched_concept = first_concept
    if title:
        title_lower = title.lower()
        best_len = -1
        for sc in semantic_concepts:
            concept = sc["final_query"]
            # Match against both the base concept and final query to be highly robust
            if sc["base_concept"].lower() in title_lower or concept.lower() in title_lower:
                if len(concept) > best_len:
                    best_len = len(concept)
                    matched_concept = concept
                    
    # 4. Deterministic categorizations
    if r_type in ["doc", "pdf", "roadmap", "document"]:
        return f"{matched_concept} Docs"
    elif r_type in ["site", "practice"]:
        return f"{matched_concept} Practice"
    else:  # video or other generic media
        return matched_concept
