from typing import List, Dict
import re

class SchedulerService:
    def parse_weeks(self, duration_str: str) -> int:
        """
        Parses text like '4 weeks' or '10 days' into a standard integer count of weeks.
        Default fallback is 2 weeks.
        """
        cleaned = duration_str.lower().strip()
        
        # Regex check for digits
        match = re.search(r'(\d+)', cleaned)
        if not match:
            return 2
            
        num = int(match.group(1))
        
        if "month" in cleaned:
            return num * 4
        elif "day" in cleaned:
            return max(1, num // 7)
        elif "week" in cleaned:
            return num
            
        return 2

    def build_plan(self, title: str, categories: List[str], resources: List[Dict], duration: str, schedule_type: str) -> List[Dict]:
        """
        Creates a sequential learning plan mapped week-by-week (or day-by-day).
        """
        weeks_count = self.parse_weeks(duration)
        plan = []

        # Categorize resources to assign them correctly to weeks
        youtube_resources = [r for r in resources if r["type"] in ["playlist", "video"]]
        doc_resources = [r for r in resources if r["type"] in ["doc", "pdf", "roadmap", "site"]]

        for w in range(1, weeks_count + 1):
            topics = []
            tasks = []
            
            # Simple division of study domains across weeks
            if categories:
                cat_idx = (w - 1) % len(categories)
                active_category = categories[cat_idx]
                topics.append(f"Mastering {active_category}")
            else:
                topics.append("Core Concept Refinement")

            # Match some video playlist/tutorial options
            if youtube_resources:
                res_idx = (w - 1) % len(youtube_resources)
                chosen_video = youtube_resources[res_idx]
                tasks.append(f"Study lesson set from: '{chosen_video['title']}' ({chosen_video['sourcePlatform']})")
            
            # Match documentation/practice sites
            if doc_resources:
                doc_idx = (w - 1) % len(doc_resources)
                chosen_doc = doc_resources[doc_idx]
                tasks.append(f"Read visual overview and docs: '{chosen_doc['title']}' at {chosen_doc['sourcePlatform']}")

            tasks.append("Complete structured review exercise and take key reference notes.")

            plan.append({
                "period": f"Week {w}",
                "topics": topics,
                "tasks": tasks
            })

        # If schedule type is daily, split the first week into a day-by-day milestone checklist
        if schedule_type.lower() == "daily":
            daily_plan = []
            days_count = min(7, weeks_count * 5)
            
            for d in range(1, days_count + 1):
                topics = []
                tasks = []
                
                cat_idx = (d - 1) % len(categories) if categories else 0
                active_category = categories[cat_idx] if categories else "Learning Topic"
                topics.append(f"Introductory {active_category}")

                if youtube_resources:
                    res_idx = (d - 1) % len(youtube_resources)
                    vid = youtube_resources[res_idx]
                    tasks.append(f"Watch 30 mins segment of: '{vid['title']}'")
                
                if doc_resources:
                    doc_idx = (d - 1) % len(doc_resources)
                    doc = doc_resources[doc_idx]
                    tasks.append(f"Solve sandbox practice on: '{doc['title']}'")

                daily_plan.append({
                    "period": f"Day {d}",
                    "topics": topics,
                    "tasks": tasks
                })
            return daily_plan

        return plan

# Singleton instance
scheduler_service = SchedulerService()
