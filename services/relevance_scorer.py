from typing import List, Dict, Set
import re

TRUSTED_PROVIDERS = [
    "freecodecamp", "mit ocw", "edx", "coursera", "khan academy", "mdn web docs", 
    "geeksforgeeks", "roadmap.sh", "leetcode", "hackerrank", "harvard", "stanford",
    "clever programmer", "traversy media", "programming with mosh", "fireship", 
    "derek banas", "academind", "web dev simplified", "techwithtim", "sentdex", "coreyms"
]

BANNED_KEYWORDS = [
    "song", "music", "lyrics", "trailer", "movie", "prank", "reaction", 
    "funny", "comedy", "shorts", "tiktok", "vlog", "cover", "gaming", "stream"
]

class RelevanceScorer:
    def filter_and_score(self, resources: List[Dict], query: str, category: str) -> List[Dict]:
        """
        Applies hard exclusions and computes a normalized 0-100 relevance score for candidate resources.
        """
        query_words = set(re.findall(r'\w+', query.lower()))
        category_words = set(re.findall(r'\w+', category.lower()))
        
        scored_list = []
        
        for item in resources:
            title = item.get("title", "").lower()
            author = item.get("channelName", "").lower()
            
            # Step 1: Hard Exclusions
            if any(banned in title for banned in BANNED_KEYWORDS):
                continue
                
            # Exclude short clips if length seconds exists
            length_seconds = item.get("lengthSeconds")
            if length_seconds is not None and length_seconds < 120:
                continue

            # Step 2: Relevance Scoring (Base score 50)
            score = 60
            
            # 1. Title Keyword Match (Up to +25)
            title_words = set(re.findall(r'\w+', title))
            match_count = len(query_words.intersection(title_words))
            score += min(match_count * 8, 25)
            
            # 2. Category Word Match (Up to +10)
            cat_match = len(category_words.intersection(title_words))
            score += min(cat_match * 5, 10)

            # 3. Source/Author Trust Boost (Up to +15)
            is_trusted = False
            for provider in TRUSTED_PROVIDERS:
                if provider in author or provider in title:
                    is_trusted = True
                    break
            
            if is_trusted:
                score += 12
            else:
                # Moderate boost for official portals
                if item.get("sourcePlatform") in ["MDN Web Docs", "roadmap.sh", "LeetCode", "HackerRank"]:
                    score += 15

            # 4. View count / engagement indicator if YouTube video (Up to +5)
            views = item.get("views", 0)
            if views > 500000:
                score += 5
            elif views > 100000:
                score += 3

            # Max cap of 99 (reserving 100 for verified curriculum standards)
            final_score = min(max(score, 30), 99)
            
            # Assign difficulty based on score or generic tag
            difficulty = "intermediate"
            if "beginner" in title or "basics" in title or "introduction" in title:
                difficulty = "beginner"
            elif "advanced" in title or "expert" in title or "deep dive" in title:
                difficulty = "advanced"

            # Create standard LearningResource structure
            scored_item = {
                "title": item.get("title"),
                "url": item.get("url"),
                "type": item.get("type"),
                "category": item.get("category", category),
                "estimatedDuration": item.get("estimatedDuration", "30 mins"),
                "thumbnail": item.get("thumbnail"),
                "sourcePlatform": item.get("sourcePlatform", "Web"),
                "difficulty": difficulty,
                "aiScore": final_score,
                "tags": list(query_words)[:4]
            }
            
            scored_list.append(scored_item)

        # Sort from highest relevance score downwards
        return sorted(scored_list, key=lambda x: x["aiScore"], reverse=True)

# Singleton instance
relevance_scorer = RelevanceScorer()
