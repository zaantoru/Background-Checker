# enhanced_backend.py
# pip install flask flask-cors requests beautifulsoup4 nltk textblob

from flask import Flask, request, jsonify
from flask_cors import CORS
from textblob import TextBlob
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import re
import json
import subprocess
import os
from urllib.parse import quote_plus

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# NEWS API KEY
NEWS_API_KEY = "f1876b55769f41c19b398ec60e01c5af"

class RedditScraper:
    """Python wrapper for the Node.js Reddit scraper"""
    
    def __init__(self):
        self.scraper_path = os.path.join(os.path.dirname(__file__), 'reddit_scraper', 'scraper.js')
    
    def scrape_reddit_mentions(self, query, subreddits, max_posts=30):
        """
        Call the Node.js scraper and return results
        """
        try:
            # Check if scraper.js exists
            if not os.path.exists(self.scraper_path):
                print(f"❌ scraper.js not found at {self.scraper_path}")
                return {'posts': [], 'total': 0, 'error': 'scraper.js not found'}
            
            # Build command
            subreddits_str = ','.join(subreddits)
            cmd = ['node', self.scraper_path, query, subreddits_str, str(max_posts)]
            
            print(f"🔧 Running: {' '.join(cmd)}")
            
            # Run the scraper
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=os.path.dirname(self.scraper_path)
            )
            
            # Check for errors in stderr (except console.error logs which go to stderr)
            if result.returncode != 0:
                error_msg = result.stderr.strip()
                print(f"❌ Scraper failed: {error_msg}")
                return {'posts': [], 'total': 0, 'error': error_msg}
            
            # Parse JSON output
            output = result.stdout.strip()
            
            # Find the JSON output (last line that's valid JSON)
            lines = output.split('\n')
            for line in reversed(lines):
                try:
                    data = json.loads(line)
                    return data
                except json.JSONDecodeError:
                    continue
            
            print("⚠️ No valid JSON output from scraper")
            return {'posts': [], 'total': 0, 'error': 'No valid output'}
            
        except subprocess.TimeoutExpired:
            print("⏰ Scraper timed out")
            return {'posts': [], 'total': 0, 'error': 'Timeout'}
        except FileNotFoundError:
            print("❌ Node.js not found. Install Node.js: https://nodejs.org/")
            return {'posts': [], 'total': 0, 'error': 'Node.js not installed'}
        except Exception as e:
            print(f"❌ Scraper error: {e}")
            return {'posts': [], 'total': 0, 'error': str(e)}

class EnhancedBackgroundChecker:
    def __init__(self):
        self.sources_checked = []
        self.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        self.reddit_scraper = RedditScraper()
    
    def analyze_sentiment_multilingual(self, text):
        """
        Analyzes sentiment for English, Tagalog, and Taglish text
        Returns: score from -1 (negative) to +1 (positive)
        """
        if not text:
            return 0
        
        # Basic sentiment using TextBlob for English
        blob = TextBlob(text)
        base_score = blob.sentiment.polarity
        
        # Filipino negative words detection
        tagalog_negative = [
            'masama', 'pangit', 'corrupt', 'scam', 'delay', 'hindi', 
            'wala', 'problema', 'issue', 'reklamo', 'complaint', 'bad',
            'poor', 'terrible', 'worst', 'bulok', 'basura', 'tanga',
            'fraud', 'fake', 'liar', 'unprofessional', 'late', 'slow',
            'walang konsiderasyon', 'walang kwenta', 'disappointing'
        ]
        
        tagalog_positive = [
            'maganda', 'mabuti', 'professional', 'trusted', 'excellent',
            'quality', 'good', 'great', 'best', 'galing', 'sulit', 
            'reliable', 'honest', 'legit', 'magaling', 'on-time', 'fast'
        ]
        
        text_lower = text.lower()
        
        # Count sentiment words
        neg_count = sum(1 for word in tagalog_negative if word in text_lower)
        pos_count = sum(1 for word in tagalog_positive if word in text_lower)
        
        # Adjust score based on Filipino words
        if neg_count > pos_count:
            base_score -= 0.3 * (neg_count - pos_count)
        elif pos_count > neg_count:
            base_score += 0.3 * (pos_count - neg_count)
        
        # Clamp between -1 and 1
        return max(-1, min(1, base_score))
    
    def extract_keywords(self, text):
        """Extract negative keywords from text"""
        negative_keywords = [
            'corrupt', 'scam', 'fraud', 'fake', 'liar', 'unprofessional',
            'masama', 'pangit', 'bulok', 'basura', 'walang konsiderasyon',
            'walang kwenta', 'delay', 'problema', 'reklamo'
        ]
        
        found = []
        text_lower = text.lower()
        for keyword in negative_keywords:
            if keyword in text_lower:
                found.append(keyword)
        
        return found
    
    def search_news_api(self, name):
        """Search for news using NewsAPI"""
        findings = []
        
        try:
            # Calculate date range (last 30 days)
            to_date = datetime.now()
            from_date = to_date - timedelta(days=30)
            
            # NewsAPI endpoint
            url = "https://newsapi.org/v2/everything"
            
            params = {
                'q': f'{name} Philippines',
                'language': 'en',
                'sortBy': 'relevancy',
                'from': from_date.strftime('%Y-%m-%d'),
                'to': to_date.strftime('%Y-%m-%d'),
                'apiKey': NEWS_API_KEY,
                'pageSize': 20
            }
            
            print(f"🔍 Searching NewsAPI for: {name}")
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                articles = data.get('articles', [])
                
                if not articles:
                    print(f"⚠️ No news found for: {name}")
                    return [{
                        'title': 'No recent news articles found',
                        'date': datetime.now().strftime('%Y-%m-%d'),
                        'source': 'NewsAPI',
                        'url': '#',
                        'snippet': f'No news coverage found for "{name}" in the past 30 days.',
                        'sentiment': 'neutral',
                        'sentiment_score': 0
                    }]
                
                for article in articles:
                    title = article.get('title', '')
                    description = article.get('description', '')
                    content = f"{title} {description}"
                    
                    # Skip if title is too short
                    if len(title) < 10:
                        continue
                    
                    # Analyze sentiment
                    sentiment_score = self.analyze_sentiment_multilingual(content)
                    
                    findings.append({
                        'title': title,
                        'date': article.get('publishedAt', '')[:10],
                        'source': article.get('source', {}).get('name', 'Unknown'),
                        'url': article.get('url', '#'),
                        'snippet': description or title,
                        'sentiment': 'positive' if sentiment_score > 0.1 else 'negative' if sentiment_score < -0.1 else 'neutral',
                        'sentiment_score': sentiment_score
                    })
                
                self.sources_checked.append({
                    'name': 'NewsAPI Search', 
                    'count': len(findings), 
                    'status': 'completed'
                })
                
                print(f"✅ Found {len(findings)} news articles")
                return findings
                
            elif response.status_code == 426:
                print("⚠️ NewsAPI rate limit reached")
                return [{
                    'title': 'News API rate limit reached',
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'source': 'System',
                    'url': '#',
                    'snippet': 'Too many requests. Please try again later.',
                    'sentiment': 'neutral',
                    'sentiment_score': 0
                }]
            else:
                print(f"❌ NewsAPI error: {response.status_code}")
                return [{
                    'title': 'News search temporarily unavailable',
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'source': 'System',
                    'url': '#',
                    'snippet': 'Unable to retrieve news at this time.',
                    'sentiment': 'neutral',
                    'sentiment_score': 0
                }]
                
        except Exception as e:
            print(f"News search error: {e}")
            return [{
                'title': 'News search error',
                'date': datetime.now().strftime('%Y-%m-%d'),
                'source': 'System',
                'url': '#',
                'snippet': f'Error: {str(e)}',
                'sentiment': 'neutral',
                'sentiment_score': 0
            }]
    
    def search_reddit(self, name):
        """Search Reddit using Puppeteer scraper"""
        social_data = []
        
        try:
            print(f"🔍 Scraping Reddit for: {name}")
            
            # Use the Node.js scraper
            result = self.reddit_scraper.scrape_reddit_mentions(
                name,
                subreddits=['Philippines', 'phcareers', 'Entrepreneurship', 'phinvest'],
                max_posts=30
            )
            
            # Check for errors
            if 'error' in result:
                print(f"⚠️ Reddit scraper error: {result['error']}")
                social_data.append({
                    'platform': 'Reddit Philippines',
                    'mentions': 0,
                    'sentiment': 'N/A',
                    'summary': f"Unable to scan Reddit: {result['error']}",
                    'sample_comments': []
                })
                self.sources_checked.append({
                    'name': 'Reddit Sentiment Scan',
                    'count': 0,
                    'status': 'unavailable'
                })
                return social_data
            
            posts = result.get('posts', [])
            total_mentions = result.get('total', 0)
            
            if not posts:
                social_data.append({
                    'platform': 'Reddit Philippines',
                    'mentions': 0,
                    'sentiment': 'N/A',
                    'summary': 'No discussions found about this entity.',
                    'sample_comments': []
                })
                self.sources_checked.append({
                    'name': 'Reddit Sentiment Scan',
                    'count': 0,
                    'status': 'completed'
                })
                return social_data
            
            # Analyze sentiment of all posts
            positive = 0
            negative = 0
            neutral = 0
            sample_comments = []
            
            for post in posts:
                full_text = post.get('full_text', '')
                sentiment_score = self.analyze_sentiment_multilingual(full_text)
                
                # Extract negative keywords
                keywords = self.extract_keywords(full_text)
                
                if sentiment_score > 0.1:
                    positive += 1
                elif sentiment_score < -0.1:
                    negative += 1
                else:
                    neutral += 1
                
                # Add to sample comments (prioritize negative ones)
                if len(sample_comments) < 5:
                    sample_comments.append({
                        'text': post.get('title', '')[:200],  # First 200 chars
                        'author': post.get('author', 'anonymous'),
                        'subreddit': post.get('subreddit', ''),
                        'score': post.get('score', 0),
                        'url': post.get('url', '#'),
                        'sentiment': 'positive' if sentiment_score > 0.1 else 'negative' if sentiment_score < -0.1 else 'neutral',
                        'keywords': keywords
                    })
            
            # Sort sample comments by negativity (show negative first)
            sample_comments.sort(key=lambda x: 0 if x['sentiment'] == 'negative' else 1 if x['sentiment'] == 'neutral' else 2)
            
            # Determine overall sentiment
            if positive > negative and positive > neutral:
                overall_sentiment = 'positive'
            elif negative > positive:
                overall_sentiment = 'negative'
            else:
                overall_sentiment = 'mixed'
            
            social_data.append({
                'platform': 'Reddit Philippines',
                'mentions': total_mentions,
                'sentiment': overall_sentiment,
                'summary': f'{positive} positive, {negative} negative, {neutral} neutral discussions found.',
                'sample_comments': sample_comments
            })
            
            self.sources_checked.append({
                'name': 'Reddit Sentiment Scan',
                'count': total_mentions,
                'status': 'completed'
            })
            
            print(f"✅ Found {total_mentions} Reddit mentions")
            
        except Exception as e:
            print(f"Reddit search error: {e}")
            social_data.append({
                'platform': 'Reddit Philippines',
                'mentions': 0,
                'sentiment': 'error',
                'summary': f'Error scanning Reddit: {str(e)}',
                'sample_comments': []
            })
            self.sources_checked.append({
                'name': 'Reddit Sentiment Scan',
                'count': 0,
                'status': 'error'
            })
        
        return social_data
    
    def check_web_presence(self, name):
        """General web presence check"""
        try:
            search_url = f"https://www.google.com/search?q={quote_plus(name + ' Philippines')}"
            headers = {'User-Agent': self.user_agent}
            response = requests.get(search_url, headers=headers, timeout=5)
            
            # Count approximate results
            soup = BeautifulSoup(response.text, 'html.parser')
            result_stats = soup.find('div', {'id': 'result-stats'})
            
            if result_stats:
                self.sources_checked.append({
                    'name': 'Google Web Search',
                    'count': 'Multiple',
                    'status': 'completed'
                })
        except:
            pass
    
    def calculate_risk(self, news, social):
        """
        Calculate risk score based ONLY on real data
        """
        score = 0
        factors = {}
        
        # NEWS ANALYSIS (70% weight)
        if news and len(news) > 0:
            # Filter out "no news" entries
            real_news = [n for n in news if 'No recent news' not in n['title'] and 'temporarily unavailable' not in n['title']]
            
            if real_news:
                news_sentiment_avg = sum([n['sentiment_score'] for n in real_news]) / len(real_news)
                
                if news_sentiment_avg < -0.3:
                    score += 50
                    factors['news'] = 'Significantly negative media coverage detected'
                elif news_sentiment_avg < -0.1:
                    score += 30
                    factors['news'] = 'Some negative media mentions found'
                elif news_sentiment_avg > 0.3:
                    score -= 10  # Bonus for good news
                    factors['news'] = 'Positive media presence confirmed'
                else:
                    score += 5
                    factors['news'] = 'Neutral media coverage'
            else:
                # No news found
                score += 15
                factors['news'] = 'Limited public media presence'
        
        # SOCIAL SENTIMENT (30% weight)
        if social and len(social) > 0:
            for s in social:
                if s['mentions'] > 0:
                    if s['sentiment'] == 'negative':
                        score += 25
                        factors['social'] = 'Negative public discussions detected'
                    elif s['sentiment'] == 'positive':
                        score -= 5
                        factors['social'] = 'Positive public sentiment'
                    elif s['sentiment'] == 'mixed':
                        score += 10
                        factors['social'] = 'Mixed public opinions'
                else:
                    score += 10
                    factors['social'] = 'No significant online discussions'
        else:
            score += 10
            factors['social'] = 'Limited social media presence'
        
        # Final score clamping
        score = max(0, min(100, score))
        
        return {
            'score': score,
            'level': 'Low' if score < 30 else 'Medium' if score < 60 else 'High',
            'recommendation': 'Approved for contracting' if score < 30 else 'Requires further review' if score < 60 else 'High risk - not recommended',
            'factors': factors
        }

@app.route('/api/background-check', methods=['POST'])
def perform_background_check():
    data = request.json
    name = data.get('name')
    
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    
    print(f"\n🔍 Starting background check for: {name}")
    
    checker = EnhancedBackgroundChecker()
    
    # Run all checks
    news = checker.search_news_api(name)  # ✅ CHANGED: Now uses NewsAPI
    social = checker.search_reddit(name)
    checker.check_web_presence(name)
    
    # Calculate risk based on REAL data only
    risk = checker.calculate_risk(news, social)
    
    print(f"✅ Analysis complete - Risk Level: {risk['level']} ({risk['score']}/100)")
    
    return jsonify({
        'subject': name,
        'timestamp': datetime.now().isoformat(),
        'risk': risk,
        'news': news,
        'social': social,
        'sources': checker.sources_checked
    })

if __name__ == '__main__':
    print("=" * 60)
    print("   🚀 ENHANCED BACKGROUND CHECKER API")
    print("   📡 Running on http://127.0.0.1:5000")
    print("=" * 60)
    print("\n📋 Configuration Status:")
    print("   ✅ NewsAPI - Active (Real news data)")
    print("   ✅ Reddit Scraper - Active (Puppeteer-based)")
    print("   ✅ Sentiment Analysis - Active (multilingual)")
    print("\n💡 To enable Reddit scraping:")
    print("   1. Install dependencies: npm install (in reddit_scraper folder)")
    print("   2. Run Chrome with remote debugging:")
    print('      "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"')
    print('      --remote-debugging-port=9222')
    print('      --user-data-dir="C:\\selenium\\chrome_profile"')
    print("\n" + "=" * 60)
    app.run(debug=True, port=5000)