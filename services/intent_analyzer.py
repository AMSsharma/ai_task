from rapidfuzz import process, fuzz
from typing import List, Dict, Set
import re
from utils.concept_utils import split_concepts

# ======================================================
# DOMAIN DICTIONARY & ALIASES
# ======================================================

STANDARD_DOMAINS = {
    "Machine Learning": [
        "ml", "machine learning", "deep learning", "dl", "neural networks", "transformers", 
        "nlp", "natural language processing", "computer vision", "cv", "reinforcement learning", 
        "pytorch", "tensorflow", "keras", "scikit-learn", "sklearn", "llm", "large language models", 
        "generative ai", "genai", "supervised learning", "unsupervised learning", "regression", 
        "classification", "clustering", "data science"
    ],
    "Frontend Development": [
        "react", "reactjs", "vue", "vuejs", "angular", "nextjs", "next.js", "svelte", 
        "javascript", "typescript", "js", "ts", "frontend", "front-end", "html", "css", 
        "tailwind", "tailwindcss", "bootstrap", "web development", "ui", "ux", "responsive design", 
        "dom", "browser", "sass", "less", "redux", "zustand"
    ],
    "Backend Development": [
        "node", "nodejs", "node.js", "express", "expressjs", "django", "fastapi", "flask", 
        "springboot", "spring boot", "backend", "back-end", "databases", "database", 
        "sql", "mysql", "postgresql", "postgres", "mongodb", "mongo", "redis", "graphql", 
        "rest api", "apis", "jwt", "authentication", "server", "orm", "prisma", "mongoose"
    ],
    "Data Structures & Algorithms": [
        "dsa", "data structures", "algorithms", "leetcode", "leet code", "graphs", "trees", 
        "binary tree", "sorting", "searching", "arrays", "linked lists", "stacks", "queues", 
        "hash maps", "hashmaps", "dynamic programming", "dp", "recursion", "greedy algorithms", 
        "time complexity", "big o", "space complexity", "competitive programming", "hackerrank"
    ],
    "DevOps & Cloud": [
        "devops", "docker", "kubernetes", "k8s", "aws", "amazon web services", "azure", 
        "gcp", "google cloud", "ci/cd", "github actions", "jenkins", "terraform", "ansible", 
        "cloud", "linux", "bash", "shell scripting", "nginx", "monitoring", "prometheus", "grafana"
    ],
    "System Design": [
        "system design", "distributed systems", "microservices", "scalability", "load balancers", 
        "caching", "sharding", "replication", "message queues", "kafka", "rabbitmq", 
        "monolith", "event driven architecture", "horizontal scaling", "vertical scaling", "cdn"
    ],
    "JEE Prep": [
        "calculus", "integration", "derivatives", "jee", "iit jee", "physics", "chemistry", 
        "organic chemistry", "inorganic chemistry", "physical chemistry", "algebra", 
        "coordinate geometry", "trigonometry", "thermodynamics", "electrostatics", 
        "mechanics", "kinematics", "vectors", "matrices", "probability"
    ]
}

DEFAULT_DOMAIN = "General Learning"

class IntentAnalyzer:
    def __init__(self):
        # Create a flattened dictionary mapping keyword -> category for quick matching
        self.keyword_to_category = {}
        for category, keywords in STANDARD_DOMAINS.items():
            for kw in keywords:
                self.keyword_to_category[kw.lower()] = category

    def clean_concept(self, concept: str) -> str:
        # Lowercase, clean extra spacing and strip punctuation
        cleaned = concept.lower().strip()
        cleaned = re.sub(r'[^\w\s\+\-\#]', '', cleaned)
        return cleaned

    def analyze(self, concepts_str: str) -> Dict[str, any]:
        """
        Parses the user-provided concepts, groups them, extracts normalized categories,
        difficulty level, and semantic tags.
        """
        # Split and purify concepts deterministically using the centralized utility
        cleaned_list = split_concepts(concepts_str)

        detected_categories = set()
        normalized_concepts = []
        tags = set()

        for raw_item in cleaned_list:
            # Fuzzy match against known keywords (using lowercase for accuracy)
            match_item = raw_item.lower().strip()
            best_match = None
            highest_score = 0
            
            match_res = process.extractOne(
                match_item, 
                self.keyword_to_category.keys(), 
                scorer=fuzz.token_sort_ratio
            )
            
            if match_res:
                matched_kw, score, _ = match_res
                if score >= 75:  # High confidence fuzzy match
                    best_match = self.keyword_to_category[matched_kw]
                    highest_score = score
                    tags.add(matched_kw)

            if best_match:
                detected_categories.add(best_match)
                normalized_concepts.append(raw_item)
            else:
                # Default logic for generic terms
                detected_categories.add(DEFAULT_DOMAIN)
                normalized_concepts.append(raw_item)
                # Add word tokens as tags
                for word in raw_item.split():
                    if len(word) > 2:
                        tags.add(word)

        # Remove 'General Learning' if specific domains were successfully matched
        if len(detected_categories) > 1 and DEFAULT_DOMAIN in detected_categories:
            detected_categories.remove(DEFAULT_DOMAIN)

        # Simple heuristic to classify difficulty
        difficulty = "intermediate"
        concepts_lower = concepts_str.lower()
        if any(x in concepts_lower for x in ["basic", "beginner", "introduction", "intro", "fundamentals", "scratch"]):
            difficulty = "beginner"
        elif any(x in concepts_lower for x in ["advanced", "expert", "deep dive", "optimization", "scalability", "architecture"]):
            difficulty = "advanced"

        return {
            "categories": sorted(list(detected_categories)),
            "normalizedConcepts": normalized_concepts,
            "difficulty": difficulty,
            "tags": sorted(list(tags))[:10]
        }

# Singleton instance
intent_analyzer = IntentAnalyzer()
