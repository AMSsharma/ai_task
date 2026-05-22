import requests
from bs4 import BeautifulSoup
import re
import urllib.parse
from typing import List, Dict
import random

# ======================================================
# CRAWLER CONFIGURATIONS
# ======================================================

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

class ResourceFetcher:
    def __init__(self):
        self.session = requests.Session()

    def _get_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "en-US,en;q=0.9"
        }

    # ======================================================
    # YOUTUBE ORGANIC SEARCH CRAWLER
    # ======================================================
    def crawl_youtube_playlists(self, query: str, limit=5) -> List[Dict]:
        """
        Directly parses YouTube organic search pages for lockupViewModels using a strict playlist search filter.
        """
        import urllib.parse
        import re
        
        # Use YouTube's strict playlist search filter
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}&sp=EgIQAw%253D%253D"
        
        playlists = []
        try:
            res = self.session.get(url, headers=self._get_headers(), timeout=10)
            if not res.ok:
                return []
                
            html = res.text
            
            # Split by lockupViewModel
            parts = html.split('"lockupViewModel":{')
            for part in parts[1:]:
                if len(playlists) >= limit:
                    break
                    
                # Extract Playlist ID
                pid_match = re.search(r'"playlistId"\s*:\s*"([a-zA-Z0-9_-]+)"', part)
                if not pid_match:
                    continue
                playlist_id = pid_match.group(1)
                
                # Skip watchlists or mix lists
                if playlist_id.startswith(("RD", "LL", "WL")):
                    continue
                    
                # Extract Title
                title = "YouTube Playlist Course"
                title_match = re.search(r'"title"\s*:\s*\{\s*"content"\s*:\s*"([^"]+)"', part)
                if title_match:
                    title = title_match.group(1)
                    try:
                        title = bytes(title, "utf-8").decode("unicode_escape")
                    except Exception:
                        pass
                
                # Extract Channel
                channel = "YouTube Educator"
                channel_match = re.search(r'"metadataParts"\s*:\s*\[\s*\{\s*"text"\s*:\s*\{\s*"content"\s*:\s*"([^"]+)"', part)
                if channel_match:
                    channel = channel_match.group(1)
                    try:
                        channel = bytes(channel, "utf-8").decode("unicode_escape")
                    except Exception:
                        pass
                
                # Extract Lesson/Video Count
                video_count = "10+ lessons"
                count_match = re.search(r'"text"\s*:\s*"(\d+\s+(?:lessons|videos))"', part)
                if count_match:
                    video_count = count_match.group(1)
                    
                # Extract Thumbnail
                thumbnail = "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=500&auto=format&fit=crop"
                thumb_match = re.search(r'"url"\s*:\s*"([^"]+)"', part)
                if thumb_match:
                    thumbnail = thumb_match.group(1).replace(r"\u0026", "&")
                    
                playlists.append({
                    "title": title.strip(),
                    "url": f"https://www.youtube.com/playlist?list={playlist_id}",
                    "type": "playlist",
                    "estimatedDuration": video_count,
                    "thumbnail": thumbnail,
                    "sourcePlatform": "YouTube",
                    "difficulty": "beginner",
                    "channelName": channel
                })
        except Exception as e:
            print(f"Error crawling YouTube playlists: {e}")
            
        return playlists

    def crawl_youtube_videos(self, query: str, limit=5) -> List[Dict]:
        """
        Directly parses YouTube organic search pages for videoRenderer cards.
        """
        search_query = f"{query} tutorial"
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(search_query)}"
        
        videos = []
        try:
            res = self.session.get(url, headers=self._get_headers(), timeout=10)
            if not res.ok:
                return []
                
            html = res.text
            section_start = html.find('"itemSectionRenderer"')
            results_section = html[section_start:section_start+400000] if section_start != -1 else html

            parts = results_section.split('"videoRenderer":{')
            for part in parts[1:]:
                if len(videos) >= limit:
                    break
                
                # Extract Video ID
                id_match = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', part)
                if not id_match:
                    continue
                video_id = id_match.group(1)

                # Extract Title
                title = ""
                title_match = re.search(r'"title":\s*\{"runs":\s*\[\s*\{\s*"text"\s*:\s*"([^"]+)"', part) or \
                              re.search(r'"title":\s*\{"simpleText":"([^"]+)"', part)
                if title_match:
                    title = title_match.group(1) or title_match.group(2)
                    try:
                        title = bytes(title, "utf-8").decode("unicode_escape")
                    except Exception:
                        pass
                
                # Extract Channel/Author
                channel = "YouTube Creator"
                channel_match = re.search(r'"ownerText":\s*\{"runs":\s*\[\s*\{\s*"text"\s*:\s*"([^"]+)"', part)
                if channel_match:
                    channel = channel_match.group(1)

                # Extract Length/Duration
                duration = "15:00"
                duration_match = re.search(r'"lengthText":\s*\{"accessibility":[^}]+?,"simpleText":"([^"]+)"', part) or \
                                 re.search(r'"lengthText":\s*\{"simpleText":"([^"]+)"', part)
                if duration_match:
                    duration = duration_match.group(1)

                # Convert duration text back into total seconds for filtering
                length_seconds = 600
                time_parts = list(map(int, duration.split(":")))
                if len(time_parts) == 2:
                    length_seconds = time_parts[0] * 60 + time_parts[1]
                elif len(time_parts) == 3:
                    length_seconds = time_parts[0] * 3600 + time_parts[1] * 60 + time_parts[2]

                # Extract View Count
                views = 10000
                views_match = re.search(r'"viewCountText":\s*\{"simpleText":"([\d,]+)\s+views"', part) or \
                              re.search(r'"viewCountText":\s*\{"runs":\s*\[\s*\{\s*"text"\s*:\s*"([\d,]+)"', part)
                if views_match:
                    views_str = views_match.group(1) or views_match.group(2)
                    views = int(views_str.replace(",", ""))

                videos.append({
                    "title": title.strip() or f"{query} Video Guide",
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "type": "video",
                    "estimatedDuration": duration,
                    "thumbnail": f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
                    "sourcePlatform": "YouTube",
                    "difficulty": "beginner",
                    "lengthSeconds": length_seconds,
                    "views": views,
                    "channelName": channel
                })
        except Exception as e:
            print(f"Error crawling YouTube videos: {e}")
            
        return videos

    # ======================================================
    # DUCKDUCKGO WEB INDEX SCRAPER (FOR DOCS, PRACTICE, ROADMAPS)
    # ======================================================
    def crawl_duckduckgo(self, query: str, site_filter: str = "", limit=5) -> List[Dict]:
        """
        Crawls DuckDuckGo HTML layout for rich document, practice, or roadmap resources.
        """
        search_query = f"site:{site_filter} {query}" if site_filter else query
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(search_query)}"
        
        results = []
        try:
            res = self.session.get(url, headers=self._get_headers(), timeout=10)
            if not res.ok:
                return []
                
            soup = BeautifulSoup(res.text, "html.parser")
            cards = soup.select(".result__body")
            
            for card in cards:
                if len(results) >= limit:
                    break
                
                url_el = card.select_one(".result__url")
                main_link_el = card.select_one(".result__snippet") or card.select_one(".result__url")
                
                href = url_el.get("href") if url_el else (main_link_el.get("href") if main_link_el else "")
                if not href:
                    continue
                    
                # Clean DDG redirect wraps
                if "uddg=" in href:
                    parts = href.split("uddg=")
                    if len(parts) > 1:
                        href = urllib.parse.unquote(parts[1].split("&")[0])

                title_el = card.select_one(".result__title")
                title = title_el.text.strip() if title_el else f"{query} Resource"
                
                snippet_el = card.select_one(".result__snippet")
                snippet = snippet_el.text.strip() if snippet_el else ""

                # Infer type
                resource_type = "doc"
                if "leetcode.com" in href or "hackerrank.com" in href:
                    resource_type = "site"
                elif "roadmap.sh" in href:
                    resource_type = "roadmap"
                elif href.endswith(".pdf") or "pdf" in title.lower():
                    resource_type = "pdf"

                # Infer Source
                source = "Web"
                if "roadmap.sh" in href:
                    source = "roadmap.sh"
                elif "developer.mozilla.org" in href:
                    source = "MDN Web Docs"
                elif "geeksforgeeks.org" in href:
                    source = "GeeksforGeeks"
                elif "leetcode.com" in href:
                    source = "LeetCode"
                elif "hackerrank.com" in href:
                    source = "HackerRank"

                results.append({
                    "title": title.split("...")[0].strip(),
                    "url": href,
                    "type": resource_type,
                    "estimatedDuration": "20 mins read",
                    "thumbnail": "https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?w=500&auto=format&fit=crop",
                    "sourcePlatform": source,
                    "difficulty": "intermediate",
                    "channelName": source,
                    "snippet": snippet
                })
        except Exception as e:
            print(f"Error scraping DuckDuckGo: {e}")
            
        return results



# Singleton instance
resource_fetcher = ResourceFetcher()
