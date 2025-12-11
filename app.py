import os
import time
import datetime
import hashlib
import json
from collections import defaultdict
from flask import Flask, render_template, jsonify, request, session
from flask_cors import CORS
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import feedparser
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logging.basicConfig(level=logging.INFO)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "newsaggregator-secret-key-2024")
CORS(app)

# NEWS SOURCES - Reduced to only chosen providers and categories
NEWS_SOURCES = {
    "World": {
        "bbc_world": {"name": "BBC World", "feed": "http://feeds.bbci.co.uk/news/world/rss.xml", "logo": "BBC", "tier": "free"},
        "nyt_world": {"name": "NY Times World", "feed": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "logo": "NYT", "tier": "premium"},
        "guardian_world": {"name": "The Guardian World", "feed": "https://www.theguardian.com/world/rss", "logo": "GDN", "tier": "free"},
        "dawn": {"name": "Dawn", "feed": "https://www.dawn.com/feeds/home", "logo": "DAWN", "tier": "free"},
        "tribune": {"name": "Express Tribune", "feed": "https://tribune.com.pk/feed/home", "logo": "ET", "tier": "free"},
        "thenews": {"name": "The News", "feed": "https://www.thenews.com.pk/rss/1/1", "logo": "NEWS", "tier": "free"},
    },
    "Politics": {
        "bbc_politics": {"name": "BBC Politics", "feed": "http://feeds.bbci.co.uk/news/politics/rss.xml", "logo": "BBC", "tier": "free"},
        "nyt_politics": {"name": "NY Times Politics", "feed": "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml", "logo": "NYT", "tier": "premium"},
        "guardian_politics": {"name": "The Guardian Politics", "feed": "https://www.theguardian.com/politics/rss", "logo": "GDN", "tier": "free"},
        "dawn_politics": {"name": "Dawn", "feed": "https://www.dawn.com/feeds/home", "logo": "DAWN", "tier": "free"},
        "tribune_politics": {"name": "Express Tribune", "feed": "https://tribune.com.pk/feed/home", "logo": "ET", "tier": "free"},
        "thenews_politics": {"name": "The News", "feed": "https://www.thenews.com.pk/rss/1/1", "logo": "NEWS", "tier": "free"},
    },
    "Business": {
        "bbc_business": {"name": "BBC Business", "feed": "http://feeds.bbci.co.uk/news/business/rss.xml", "logo": "BBC", "tier": "free"},
        "nyt_business": {"name": "NY Times Business", "feed": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "logo": "NYT", "tier": "premium"},
        "guardian_business": {"name": "The Guardian Business", "feed": "https://www.theguardian.com/business/rss", "logo": "GDN", "tier": "free"},
        "dawn_business": {"name": "Dawn", "feed": "https://www.dawn.com/feeds/home", "logo": "DAWN", "tier": "free"},
        "tribune_business": {"name": "Express Tribune", "feed": "https://tribune.com.pk/feed/home", "logo": "ET", "tier": "free"},
        "thenews_business": {"name": "The News", "feed": "https://www.thenews.com.pk/rss/1/1", "logo": "NEWS", "tier": "free"},
    },
    "Sports": {
        "bbc_sport": {"name": "BBC Sport", "feed": "http://feeds.bbci.co.uk/sport/rss.xml", "logo": "BBC", "tier": "free"},
        "nyt_sport": {"name": "NY Times Sports", "feed": "https://rss.nytimes.com/services/xml/rss/nyt/Sports.xml", "logo": "NYT", "tier": "premium"},
        "guardian_sport": {"name": "The Guardian Sport", "feed": "https://www.theguardian.com/sport/rss", "logo": "GDN", "tier": "free"},
        "espncricinfo": {"name": "ESPNcricinfo", "feed": "https://www.espncricinfo.com/rss/content/story/feeds/0.xml", "logo": "ESPC", "tier": "free"},
        "dawn_sport": {"name": "Dawn", "feed": "https://www.dawn.com/feeds/home", "logo": "DAWN", "tier": "free"},
        "tribune_sport": {"name": "Express Tribune", "feed": "https://tribune.com.pk/feed/home", "logo": "ET", "tier": "free"},
        "thenews_sport": {"name": "The News", "feed": "https://www.thenews.com.pk/rss/1/1", "logo": "NEWS", "tier": "free"},
    },
}

# Enhanced cache
CACHE = {
    "all_articles": [],
    "by_category": {},
    "by_source": {},
    "trending": [],
    "personalized": {},
    "clusters": [],
    "sentiment": {},
    "fetched_at": 0,
    "stats": {},
    "failed_sources": []
}
CACHE_TTL = 300

def analyze_sentiment(text):
    """Enhanced sentiment analysis"""
    positive_words = ['breakthrough', 'success', 'growth', 'innovation', 'win', 'achievement', 'record', 'profit', 'gain', 'improve', 'advance', 'positive', 'excellent', 'outstanding']
    negative_words = ['crisis', 'crash', 'decline', 'threat', 'conflict', 'war', 'death', 'disaster', 'scandal', 'controversial', 'failure', 'loss', 'negative', 'worst']
    
    text_lower = text.lower()
    pos_count = sum(1 for word in positive_words if word in text_lower)
    neg_count = sum(1 for word in negative_words if word in text_lower)
    
    if pos_count > neg_count:
        return "positive"
    elif neg_count > pos_count:
        return "negative"
    return "neutral"

def cluster_similar_articles(articles, n_clusters=5):
    """Cluster similar articles using TF-IDF"""
    if len(articles) < 3:
        return []
    
    try:
        texts = [f"{a['title']} {a['snippet']}" for a in articles[:100]]
        vectorizer = TfidfVectorizer(max_features=100, stop_words='english')
        tfidf_matrix = vectorizer.fit_transform(texts)
        
        similarity_matrix = cosine_similarity(tfidf_matrix)
        
        clusters = []
        seen = set()
        
        for i, article in enumerate(articles[:100]):
            if i in seen:
                continue
            
            similar_indices = np.where(similarity_matrix[i] > 0.3)[0]
            if len(similar_indices) > 1:
                cluster = {
                    "main_article": article,
                    "related": [articles[j] for j in similar_indices if j != i and j < len(articles)],
                    "count": len(similar_indices)
                }
                clusters.append(cluster)
                seen.update(similar_indices)
        
        return sorted(clusters, key=lambda x: x['count'], reverse=True)[:n_clusters]
    except Exception as e:
        logger.error(f"Error clustering articles: {e}")
        return []


def prioritize_world_articles(articles):
    """Place World category articles at the front while preserving recency/trending"""
    try:
        world = [a for a in articles if a.get('category') == 'World']
        others = [a for a in articles if a.get('category') != 'World']

        # Sort world by trending_score then published
        world.sort(key=lambda x: (-(x.get('trending_score', 0)), x.get('published')), reverse=False)

        # Keep others as-is (already sorted by published desc)
        return world + others
    except Exception as e:
        logger.debug(f"Error prioritizing world articles: {e}")
        return articles

def calculate_trending_score(article):
    """Calculate trending score"""
    try:
        now = datetime.datetime.now()
        pub_date = article.get('published', now)
        
        hours_old = (now - pub_date).total_seconds() / 3600
        recency_score = max(0, 100 - hours_old)
        
        trending_keywords = ['breaking', 'just in', 'urgent', 'alert', 'developing', 'live', 'exclusive', 'update']
        keyword_score = sum(20 for kw in trending_keywords if kw in article['title'].lower())
        
        return recency_score + keyword_score
    except:
        return 0

def extract_image_from_entry(entry, link=None):
    """Enhanced image extraction"""
    try:
        # Try common media fields (handle many feed variations and namespaces)
        for media_key in ["media_content", "media:content", "media_thumbnail", "media:thumbnail", "enclosures", "media_contents", "media"]:
            media = entry.get(media_key)
            if not media:
                continue
            try:
                if isinstance(media, list) and media:
                    first = media[0]
                    if isinstance(first, dict):
                        url = first.get("url") or first.get("href") or first.get("media_url") or first.get("@url") or first.get("src")
                        if url:
                            return resolve_url(url, link)
                    elif isinstance(first, str):
                        return resolve_url(first, link)
                elif isinstance(media, dict):
                    url = media.get("url") or media.get("href") or media.get("media_url") or media.get("@url") or media.get("src")
                    if url:
                        return resolve_url(url, link)
                elif isinstance(media, str):
                    return resolve_url(media, link)
            except Exception:
                # continue trying other methods; do not let one malformed media block break extraction
                continue
        
        for link_item in entry.get("links", []) or []:
            try:
                if isinstance(link_item, dict) and link_item.get("type", "").startswith("image"):
                    href = link_item.get("href") or link_item.get("href:lang")
                    if href:
                        return resolve_url(href, link)
            except Exception:
                continue
        
        for img_field in ["image", "thumbnail", "img"]:
            img = entry.get(img_field)
            if not img:
                continue
            try:
                if isinstance(img, dict):
                    url = img.get("href") or img.get("url") or img.get("src") or img.get("@url")
                    if url:
                        return resolve_url(url, link)
                elif isinstance(img, str):
                    return resolve_url(img, link)
            except Exception:
                continue
        
        html_content = entry.get("summary") or entry.get("summary_detail", {}).get("value") or ""
        if entry.get("content"):
            try:
                content_item = entry.get("content")[0]
                if isinstance(content_item, dict):
                    html_content = content_item.get("value", "") or content_item.get("src", "") or html_content
                else:
                    html_content = str(content_item) or html_content
            except Exception:
                # be resilient to unexpected content shapes
                pass

        if html_content:
            img = extract_image_from_html(html_content, link)
            if img:
                return resolve_url(img, link)

        # As a last resort, search the whole entry object for image urls (handles nested media namespaces)
        found = find_image_url_in_obj(entry, base_url=link)
        if found:
            return resolve_url(found, link)
    except Exception as e:
        logger.debug(f"Error extracting image: {e}")
    
    return None


def resolve_url(url, base=None):
    """Resolve relative and protocol-relative URLs to absolute form."""
    try:
        if not url:
            return None
        url = url.strip()
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/") and base:
            parsed = urlparse(base)
            return f"{parsed.scheme}://{parsed.netloc}{url}"
        if url.startswith("http://") or url.startswith("https://"):
            return url
        # sometimes urls are missing scheme
        if url.startswith("www."):
            return "https://" + url
        return url
    except Exception:
        return url

def extract_image_from_html(html_text, base_url=None):
    """Extract image from HTML"""
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            return og_img["content"]
        
        tw_img = soup.find("meta", attrs={"name": "twitter:image"})
        if tw_img and tw_img.get("content"):
            return tw_img["content"]
        
        # Prefer <picture> or <figure> sources
        picture = soup.find(["picture", "figure"]) 
        if picture:
            # look for <img> or <source>
            source_img = picture.find("img") or picture.find("source")
            if source_img:
                src = source_img.get("src") or source_img.get("data-src") or source_img.get("data-original") or source_img.get("data-lazy-src") or source_img.get("data-srcset") or source_img.get("srcset")
                if src:
                    # if srcset, take first url
                    if "," in src and "http" in src:
                        src = src.split(",")[0].strip().split(" ")[0]
                    if src.startswith("//"):
                        return "https:" + src
                    elif src.startswith("/") and base_url:
                        parsed = urlparse(base_url)
                        return f"{parsed.scheme}://{parsed.netloc}{src}"
                    elif src.startswith("http"):
                        return src

        img = soup.find("img")
        if img:
            # check several possible attributes used by lazy loading
            src = img.get("src") or img.get("data-src") or img.get("data-original") or img.get("data-lazy-src") or img.get("data-srcset") or img.get("srcset")
            if src:
                if "," in src and "http" in src:
                    src = src.split(",")[0].strip().split(" ")[0]
                if src.startswith("//"):
                    return "https:" + src
                elif src.startswith("/") and base_url:
                    parsed = urlparse(base_url)
                    return f"{parsed.scheme}://{parsed.netloc}{src}"
                elif src.startswith("http"):
                    return src
    except Exception as e:
        logger.debug(f"Error extracting image from HTML: {e}")
    
    return None


def find_image_url_in_obj(obj, base_url=None):
    """Recursively search a nested object (dict/list/str) for an image URL."""
    try:
        if not obj:
            return None

        if isinstance(obj, str):
            s = obj.strip()
            # simple heuristics
            if s.startswith("//"):
                return "https:" + s
            if s.startswith("http") and any(ext in s.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
                return s
            return None

        if isinstance(obj, dict):
            for k, v in obj.items():
                # common keys that may contain urls
                if isinstance(v, str):
                    if v.startswith("//"):
                        return "https:" + v
                    if v.startswith("http") and any(ext in v.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
                        return v
                elif isinstance(v, (dict, list)):
                    found = find_image_url_in_obj(v, base_url=base_url)
                    if found:
                        return found

        if isinstance(obj, list):
            for item in obj:
                found = find_image_url_in_obj(item, base_url=base_url)
                if found:
                    return found

    except Exception as e:
        logger.debug(f"Error searching object for image url: {e}")

    return None

def parse_published_date(entry):
    """Parse published date"""
    try:
        for time_field in ["published_parsed", "updated_parsed", "created_parsed"]:
            t = entry.get(time_field)
            if t:
                try:
                    return datetime.datetime.fromtimestamp(time.mktime(t))
                except:
                    pass
        
        for date_field in ["published", "updated", "created"]:
            date_str = entry.get(date_field)
            if date_str:
                try:
                    for fmt in ["%a, %d %b %Y %H:%M:%S %z", 
                               "%Y-%m-%dT%H:%M:%S%z", 
                               "%Y-%m-%d %H:%M:%S",
                               "%Y-%m-%dT%H:%M:%SZ"]:
                        try:
                            return datetime.datetime.strptime(date_str, fmt)
                        except:
                            continue
                except:
                    pass
    except Exception as e:
        logger.debug(f"Error parsing date: {e}")
    
    return datetime.datetime.now()

def generate_article_id(title, link):
    """Generate unique ID"""
    try:
        unique_string = f"{title}{link}".encode('utf-8')
        return hashlib.md5(unique_string).hexdigest()[:16]
    except:
        return hashlib.md5(str(time.time()).encode()).hexdigest()[:16]

def clean_text(text):
    """Clean text"""
    if not text:
        return ""
    try:
        soup = BeautifulSoup(text, "html.parser")
        clean = soup.get_text().strip()
        return clean[:300] + "..." if len(clean) > 300 else clean
    except:
        return str(text)[:300]

def fetch_single_feed(source_key, source_info, category, limit=None):
    """Fetch articles from RSS feed"""
    articles = []
    try:
        # Limit lightweight fallback page fetches per feed to avoid long blocking
        fallback_attempts = 0
        max_fallbacks = 3
        feed_url = source_info["feed"]
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        # Simple retry/backoff to improve reliability
        attempt = 0
        response = None
        while attempt < 2:
            try:
                response = requests.get(feed_url, headers=headers, timeout=15, allow_redirects=True)
                response.raise_for_status()
                break
            except requests.exceptions.RequestException as e:
                attempt += 1
                logger.warning(f"Attempt {attempt} failed for {source_info['name']}: {e}")
                time.sleep(1 * attempt)

        if response is None:
            logger.error(f"Failed to fetch feed for {source_info['name']} after retries")
            return articles

        parsed_feed = feedparser.parse(response.content)

        if not parsed_feed.entries:
            logger.warning(f"No entries for {source_info['name']}")
            return articles

        logger.info(f"✓ {source_info['name']}: {len(parsed_feed.entries)} entries")

        entries = parsed_feed.entries if limit is None else parsed_feed.entries[:limit]
        for entry in entries:
            try:
                title = entry.get("title", "No Title")
                link = entry.get("link", "")
                
                if not link or not title:
                    continue
                
                snippet = clean_text(entry.get("summary", entry.get("description", "")))
                
                article = {
                    "id": generate_article_id(title, link),
                    "title": title,
                    "link": link,
                    "snippet": snippet,
                    "image": extract_image_from_entry(entry, link),
                    "source": source_info["name"],
                    "source_key": source_key,
                    "source_logo": source_info["logo"],
                    "category": category,
                    "tier": source_info.get("tier", "free"),
                    "published": parse_published_date(entry),
                    "fetched_at": datetime.datetime.now(),
                    "sentiment": analyze_sentiment(title + " " + snippet),
                    "trending_score": 0
                }

                # If image missing, do a lightweight page fetch fallback but only for high-value sources
                # and limit number of fallbacks per feed to avoid long-running fetches that cause executor timeouts.
                if (not article.get('image') and link
                    and fallback_attempts < max_fallbacks
                    and (source_key.startswith('cnn') or 'aljazeera' in source_key)):
                    try:
                        fallback_attempts += 1
                        # shorter timeout to avoid blocking the worker
                        page_resp = requests.get(link, headers=headers, timeout=3)
                        if page_resp.ok and page_resp.text:
                            img_from_page = extract_image_from_html(page_resp.text, link)
                            if img_from_page:
                                article['image'] = resolve_url(img_from_page, link)
                    except Exception as e:
                        logger.debug(f"Fallback image fetch failed for {link}: {e}")

                article["trending_score"] = calculate_trending_score(article)
                articles.append(article)
                
            except Exception as e:
                logger.debug(f"Error parsing entry: {e}")
                continue
                
    except requests.exceptions.Timeout:
        logger.error(f"⏱️ Timeout: {source_info['name']}")
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Error: {source_info['name']}: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {source_info['name']}: {e}")
    
    return articles

def aggregate_all_news(max_per_source=None, use_cache=True):
    """Aggregate all news"""
    now = time.time()
    
    if use_cache and CACHE["all_articles"] and (now - CACHE["fetched_at"] < CACHE_TTL):
        logger.info("✓ Returning cached articles")
        return CACHE["all_articles"]
    
    logger.info("🔄 Fetching fresh articles...")
    all_articles = []
    articles_by_category = defaultdict(list)
    articles_by_source = defaultdict(list)
    failed_sources_set = set()

    successful_fetches = 0
    failed_fetches = 0
    
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = []
        
        for category, sources in NEWS_SOURCES.items():
            for source_key, source_info in sources.items():
                future = executor.submit(
                    fetch_single_feed, 
                    source_key, 
                    source_info, 
                    category, 
                    max_per_source
                )
                futures.append((future, source_info['name']))
        
        for future, source_name in futures:
            try:
                articles = future.result(timeout=20)
                if articles:
                    all_articles.extend(articles)
                    successful_fetches += 1

                    for article in articles:
                        articles_by_category[article["category"]].append(article)
                        articles_by_source[article["source"]].append(article)
                else:
                    failed_fetches += 1
                    failed_sources_set.add(source_name)
            except Exception as e:
                logger.error(f"❌ Error processing {source_name}: {e}")
                failed_fetches += 1
                failed_sources_set.add(source_name)
    
    # Remove duplicates
    seen_ids = set()
    unique_articles = []
    for article in all_articles:
        if article["id"] not in seen_ids:
            seen_ids.add(article["id"])
            unique_articles.append(article)
    
    # Sort by date
    unique_articles.sort(key=lambda x: x["published"], reverse=True)

    # Prioritize World category for front page
    unique_articles = prioritize_world_articles(unique_articles)

    trending = sorted(unique_articles, key=lambda x: x["trending_score"], reverse=True)[:30]
    clusters = cluster_similar_articles(unique_articles)
    
    CACHE["all_articles"] = unique_articles
    CACHE["by_category"] = dict(articles_by_category)
    CACHE["by_source"] = dict(articles_by_source)
    CACHE["trending"] = trending
    CACHE["clusters"] = clusters
    # Front page: only World and Politics, newest first
    try:
        front = [a for a in unique_articles if a.get('category') in ('World', 'Politics')]
        front.sort(key=lambda x: x['published'], reverse=True)
        CACHE['front_page'] = front
    except Exception as e:
        logger.debug(f"Error preparing front_page cache: {e}")
    CACHE["fetched_at"] = now
    CACHE["failed_sources"] = sorted(list(failed_sources_set))
    CACHE["stats"] = {
        "total_articles": len(unique_articles),
        "categories": len(articles_by_category),
        "sources": len(articles_by_source),
        "trending_count": len(trending),
        "clusters": len(clusters),
        "last_updated": datetime.datetime.now().isoformat(),
        "successful_fetches": successful_fetches,
        "failed_fetches": failed_fetches,
        "success_rate": f"{(successful_fetches/(successful_fetches+failed_fetches)*100):.1f}%" if (successful_fetches+failed_fetches) > 0 else "0%"
    }
    
    logger.info(f"✓ Fetched {len(unique_articles)} unique articles from {successful_fetches} sources")
    
    return unique_articles

# --- API ROUTES ---
@app.route("/")
def index():
    try:
        # Trigger initial fetch if needed
        if not CACHE["all_articles"]:
            aggregate_all_news()
        # Prepare front page: only World and Politics, newest first
        try:
            if not CACHE.get('front_page'):
                aggregate_all_news()
            front_articles = CACHE.get('front_page', [])[:50]
        except Exception:
            front_articles = []

        # Pass front page articles to template for rendering
        return render_template("index.html", front_articles=front_articles)
    except Exception as e:
        logger.error(f"Error rendering index: {e}")
        return f"Error loading page: {str(e)}", 500

@app.route("/api/articles")
def api_articles():
    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 50, type=int)
        category = request.args.get("category")
        source = request.args.get("source")
        sentiment = request.args.get("sentiment")
        tier = request.args.get("tier")
        
        articles = aggregate_all_news()
        
        if category:
            articles = [a for a in articles if a["category"] == category]
        
        if source:
            articles = [a for a in articles if a["source_key"] == source]
        
        if sentiment:
            articles = [a for a in articles if a.get("sentiment") == sentiment]
        
        if tier:
            articles = [a for a in articles if a.get("tier") == tier]
        
        start = (page - 1) * per_page
        end = start + per_page
        paginated = articles[start:end]
        
        return jsonify({
            "articles": paginated,
            "total": len(articles),
            "page": page,
            "per_page": per_page,
            "total_pages": (len(articles) + per_page - 1) // per_page
        })
    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/trending")
def api_trending():
    try:
        aggregate_all_news()
        return jsonify({"trending": CACHE.get("trending", [])[:30]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/clusters")
def api_clusters():
    try:
        aggregate_all_news()
        return jsonify({"clusters": CACHE.get("clusters", [])})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/frontpage")
def api_frontpage():
    try:
        aggregate_all_news()
        return jsonify({"front": CACHE.get("front_page", [])[:50]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/track", methods=["POST"])
def api_track():
    try:
        data = request.json
        user_id = session.get("user_id", "anonymous")
        
        if user_id not in CACHE["personalized"]:
            CACHE["personalized"][user_id] = {"categories": [], "sources": []}
        
        category = data.get("category")
        source = data.get("source")
        
        if category and category not in CACHE["personalized"][user_id]["categories"]:
            CACHE["personalized"][user_id]["categories"].append(category)
        
        if source and source not in CACHE["personalized"][user_id]["sources"]:
            CACHE["personalized"][user_id]["sources"].append(source)
        
        return jsonify({"status": "tracked"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/stats")
def api_stats():
    return jsonify(CACHE.get("stats", {}))

@app.route("/api/search")
def api_search():
    try:
        query = request.args.get("q", "").lower()
        
        if not query:
            return jsonify({"error": "Query required"}), 400
        
        articles = aggregate_all_news()
        
        results = [
            a for a in articles 
            if query in a["title"].lower() or query in a["snippet"].lower()
        ]
        
        return jsonify({
            "results": results,
            "total": len(results),
            "query": query
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/refresh")
def api_refresh():
    try:
        CACHE["fetched_at"] = 0
        articles = aggregate_all_news(use_cache=False)
        return jsonify({
            "message": "Refreshed",
            "total_articles": len(articles),
            "stats": CACHE.get("stats", {})
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/health")
def api_health():
    return jsonify({
        "status": "healthy",
        "cache_age": time.time() - CACHE["fetched_at"],
        "total_articles": len(CACHE["all_articles"]),
        "failed_sources": CACHE.get("failed_sources", [])
    })

@app.route("/debug")
def debug():
    """Debug endpoint to check file paths"""
    template_path = os.path.join(app.root_path, 'templates', 'index.html')
    return jsonify({
        "current_dir": os.getcwd(),
        "app_root_path": app.root_path,
        "template_folder": app.template_folder,
        "files_in_root": os.listdir('.'),
        "templates_exists": os.path.exists('templates'),
        "files_in_templates": os.listdir('templates') if os.path.exists('templates') else [],
        "index_html_exists": os.path.exists(template_path),
        "index_html_path": template_path
    })

if __name__ == "__main__":
    logger.info("🚀 Starting Professional News Aggregator...")
    
    # Verify templates folder exists
    if os.path.exists('templates'):
        logger.info(f"✓ Templates folder found")
        if os.path.exists('templates/index.html'):
            logger.info(f"✓ index.html found in templates folder")
        else:
            logger.error(f"❌ index.html NOT found in templates folder")
    else:
        logger.error(f"❌ Templates folder NOT found")
    
    try:
        aggregate_all_news(use_cache=False)
        logger.info("✓ Initial news fetch complete")
    except Exception as e:
        logger.error(f"❌ Error during initial fetch: {e}")
    
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)