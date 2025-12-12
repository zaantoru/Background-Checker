// reddit_scraper/scraper.js
// Usage: node scraper.js "search_query" "Philippines,phcareers" "50"

const puppeteer = require('puppeteer-core');

class RedditScraper {
    constructor() {
        this.browser = null;
        this.page = null;
        this.posts = [];
        this.comments = [];
    }

    async connect() {
        try {
            // Connect to existing Chrome instance
            this.browser = await puppeteer.connect({
                browserURL: 'http://localhost:9222',
                defaultViewport: null
            });
            return true;
        } catch (error) {
            console.error('Failed to connect to Chrome:', error.message);
            return false;
        }
    }

    // Helper function to wait (replacement for deprecated waitForTimeout)
    async wait(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    async scrapeSearch(query, subreddits, maxPosts = 50) {
        this.page = await this.browser.newPage();
        
        // Set up request interception to capture Reddit API calls
        await this.page.setRequestInterception(true);
        
        const interceptedData = [];
        
        this.page.on('request', request => {
            request.continue();
        });

        this.page.on('response', async response => {
            try {
                const url = response.url();
                
                // Intercept Reddit's GraphQL API or JSON responses
                if (url.includes('reddit.com') && 
                    (url.includes('.json') || url.includes('graphql') || url.includes('api'))) {
                    
                    const contentType = response.headers()['content-type'] || '';
                    
                    if (contentType.includes('application/json')) {
                        const data = await response.json();
                        interceptedData.push(data);
                    }
                }
            } catch (error) {
                // Ignore parsing errors
            }
        });

        // Search each subreddit
        for (const subreddit of subreddits) {
            if (this.posts.length >= maxPosts) break;
            
            const searchUrl = `https://old.reddit.com/r/${subreddit}/search?q=${encodeURIComponent(query)}&restrict_sr=on&sort=relevance&t=all`;
            
            console.error(`Searching r/${subreddit}...`);
            
            await this.page.goto(searchUrl, {
                waitUntil: 'networkidle2',
                timeout: 30000
            });

            // FIXED: Use custom wait function instead of waitForTimeout
            await this.wait(2000);

            // Extract posts from intercepted data
            this.extractPosts(interceptedData);

            // Also scrape HTML directly as fallback
            await this.scrapeHTML();
        }

        await this.page.close();
        
        return {
            posts: this.posts.slice(0, maxPosts),
            comments: this.comments,
            total: this.posts.length
        };
    }

    extractPosts(interceptedData) {
        for (const data of interceptedData) {
            try {
                // Reddit's JSON structure
                if (data.data && data.data.children) {
                    for (const child of data.data.children) {
                        const post = child.data;
                        
                        if (post && post.title) {
                            this.posts.push({
                                id: post.id,
                                title: post.title,
                                text: post.selftext || '',
                                author: post.author,
                                subreddit: post.subreddit,
                                score: post.score,
                                upvote_ratio: post.upvote_ratio,
                                num_comments: post.num_comments,
                                created: post.created_utc,
                                url: `https://reddit.com${post.permalink}`,
                                full_text: `${post.title} ${post.selftext || ''}`
                            });
                        }
                    }
                }
            } catch (error) {
                // Continue on error
            }
        }
    }

    async scrapeHTML() {
        // Fallback: scrape HTML if API interception fails
        try {
            const posts = await this.page.$$('.search-result-link');
            
            for (const post of posts) {
                try {
                    const title = await post.$eval('.search-title', el => el.textContent.trim());
                    const link = await post.$eval('.search-title', el => el.href);
                    const subreddit = await post.$eval('.search-subreddit-link', el => el.textContent.trim());
                    const author = await post.$eval('.author', el => el.textContent.trim());
                    const score = await post.$eval('.search-score', el => el.textContent.trim());
                    const time = await post.$eval('.search-time', el => el.getAttribute('datetime'));
                    
                    // Avoid duplicates
                    const postId = link.split('/comments/')[1]?.split('/')[0];
                    
                    if (postId && !this.posts.some(p => p.id === postId)) {
                        this.posts.push({
                            id: postId,
                            title: title,
                            text: '',
                            author: author,
                            subreddit: subreddit.replace('r/', ''),
                            score: parseInt(score) || 0,
                            upvote_ratio: null,
                            num_comments: 0,
                            created: new Date(time).getTime() / 1000,
                            url: link,
                            full_text: title
                        });
                    }
                } catch (e) {
                    // Skip failed posts
                }
            }
        } catch (error) {
            console.error('HTML scraping fallback failed:', error.message);
        }
    }

    async disconnect() {
        if (this.browser) {
            await this.browser.disconnect();
        }
    }
}

// Main execution
(async () => {
    const args = process.argv.slice(2);
    
    if (args.length < 3) {
        console.error('Usage: node scraper.js "query" "sub1,sub2,sub3" "maxPosts"');
        process.exit(1);
    }

    const [query, subredditsStr, maxPostsStr] = args;
    const subreddits = subredditsStr.split(',').map(s => s.trim());
    const maxPosts = parseInt(maxPostsStr) || 50;

    const scraper = new RedditScraper();
    
    const connected = await scraper.connect();
    if (!connected) {
        console.error(JSON.stringify({ error: 'Failed to connect to Chrome' }));
        process.exit(1);
    }

    try {
        const result = await scraper.scrapeSearch(query, subreddits, maxPosts);
        console.log(JSON.stringify(result));
    } catch (error) {
        console.error(JSON.stringify({ error: error.message }));
        process.exit(1);
    } finally {
        await scraper.disconnect();
    }
})();