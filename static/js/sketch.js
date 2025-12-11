        const FRONT_ARTICLES = null;

        let allArticles = [];
        let displayedArticles = [];
        let currentCategory = 'home';
        let currentView = 'grid';
        let currentPage = 1;
        const articlesPerPage = 50;

        // Initialize
        document.addEventListener('DOMContentLoaded', () => {
            loadTheme();
            setupEventListeners();
            setupScrollListener();

            if (typeof FRONT_ARTICLES !== 'undefined' && FRONT_ARTICLES && FRONT_ARTICLES.length) {
                allArticles = FRONT_ARTICLES;
                displayedArticles = [...allArticles];
                fetchStats();
                renderArticles();
            } else {
                fetchNews();
            }
        });

        // Theme Toggle
        function toggleTheme() {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            
            const themeIcon = document.getElementById('themeIcon');
            themeIcon.className = newTheme === 'light' ? 'fas fa-sun' : 'fas fa-moon';
        }

        function loadTheme() {
            const savedTheme = localStorage.getItem('theme') || 'dark';
            document.documentElement.setAttribute('data-theme', savedTheme);
            const themeIcon = document.getElementById('themeIcon');
            themeIcon.className = savedTheme === 'light' ? 'fas fa-sun' : 'fas fa-moon';
        }

        // Setup Event Listeners
        function setupEventListeners() {
            // Category navigation
            document.querySelectorAll('.nav-item').forEach(item => {
                item.addEventListener('click', function() {
                    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
                    this.classList.add('active');
                    currentCategory = this.dataset.category;
                    currentPage = 1;
                    fetchNews(); // Fetch fresh articles for the category
                });
            });

            // Search on Enter
            document.getElementById('searchInput').addEventListener('keypress', (e) => {
                if (e.key === 'Enter') searchNews();
            });
        }

        // Setup Scroll Listener
        function setupScrollListener() {
            const scrollBtn = document.getElementById('scrollTop');
            window.addEventListener('scroll', () => {
                if (window.pageYOffset > 300) {
                    scrollBtn.classList.add('visible');
                } else {
                    scrollBtn.classList.remove('visible');
                }
            });
        }

        // Fetch News
        async function fetchNews() {
            try {
                showLoading();
                let url = '/api/articles?per_page=500';
                
                // Add category parameter if not home or all
                if (currentCategory !== 'home' && currentCategory !== 'all') {
                    url += `&category=${encodeURIComponent(currentCategory)}`;
                }
                
                const response = await fetch(url);
                const data = await response.json();
                allArticles = data.articles || [];
                displayedArticles = [...allArticles];
                
                await fetchStats();
                renderArticles();
                hideLoading();
            } catch (error) {
                console.error('Error fetching news:', error);
                showError('Failed to load news. Please try again.');
            }
        }

        // Fetch Stats
        async function fetchStats() {
            try {
                const response = await fetch('/api/stats');
                const stats = await response.json();
                updateStats(stats);
            } catch (error) {
                console.error('Error fetching stats:', error);
            }
        }

        // Update Stats
        function updateStats(stats) {
            document.getElementById('totalArticles').textContent = stats.total_articles || 0;
            document.getElementById('trendingCount').textContent = stats.trending_count || 0;
            document.getElementById('sourcesCount').textContent = stats.sources || 0;
            document.getElementById('successRate').textContent = stats.success_rate || '0%';
        }

        // Apply Filters
        function applyFilters() {
            let filtered = [...allArticles];

            // Category filter
            if (currentCategory === 'home') {
                // Home page shows all articles from all categories
                document.getElementById('sectionTitle').textContent = 'Home - Featured News';
            } else if (currentCategory !== 'all') {
                // Already filtered by API based on currentCategory
                document.getElementById('sectionTitle').textContent = `${currentCategory} News`;
            } else {
                document.getElementById('sectionTitle').textContent = 'Latest News';
            }

            // Sentiment filter
            const sentiment = document.getElementById('sentimentFilter').value;
            if (sentiment) {
                filtered = filtered.filter(a => a.sentiment === sentiment);
            }

            // Tier filter
            const tier = document.getElementById('tierFilter').value;
            if (tier) {
                filtered = filtered.filter(a => a.tier === tier);
            }

            // Sort
            const sort = document.getElementById('sortFilter').value;
            if (sort === 'trending') {
                filtered.sort((a, b) => (b.trending_score || 0) - (a.trending_score || 0));
            } else if (sort === 'source') {
                filtered.sort((a, b) => a.source.localeCompare(b.source));
            } else {
                filtered.sort((a, b) => new Date(b.published) - new Date(a.published));
            }

            displayedArticles = filtered;
            currentPage = 1;
            renderArticles();
        }

        // Search News
        async function searchNews() {
            const query = document.getElementById('searchInput').value.trim();
            if (!query) {
                displayedArticles = [...allArticles];
                renderArticles();
                return;
            }

            try {
                showLoading();
                const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
                const data = await response.json();
                displayedArticles = data.results || [];
                document.getElementById('sectionTitle').textContent = `Search: "${query}"`;
                renderArticles();
                hideLoading();
            } catch (error) {
                console.error('Error searching:', error);
                showError('Search failed. Please try again.');
            }
        }

        // Render Articles
        function renderArticles() {
            const grid = document.getElementById('newsGrid');
            
            // Special rendering for home page
            if (currentCategory === 'home') {
                renderHomePageArticles(grid);
                return;
            }
            
            const start = 0;
            const end = currentPage * articlesPerPage;
            const articles = displayedArticles.slice(start, end);

            if (articles.length === 0) {
                grid.innerHTML = `
                    <div style="grid-column: 1/-1; text-align: center; padding: 3rem;">
                        <i class="fas fa-inbox" style="font-size: 4rem; color: var(--text-muted); margin-bottom: 1rem;"></i>
                        <h3>No articles found</h3>
                        <p style="color: var(--text-muted);">Try adjusting your filters or search query</p>
                    </div>
                `;
                return;
            }

            grid.innerHTML = articles.map(article => createArticleCard(article)).join('');
        }

        // Render Home Page with Categories
        function renderHomePageArticles(grid) {
            const categories = ['World', 'Politics', 'Business', 'Sports'];
            const articlesPerCategory = 6;
            
            let htmlContent = '';

            categories.forEach(category => {
                const categoryArticles = displayedArticles
                    .filter(a => a.category === category)
                    .slice(0, articlesPerCategory);

                if (categoryArticles.length === 0) return;

                htmlContent += `
                    <div style="grid-column: 1/-1; margin-top: 2rem; margin-bottom: 1rem;">
                        <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1.5rem;">
                            <h2 style="font-size: 1.8rem; margin: 0;">
                                <i class="fas fa-${getCategoryIcon(category)}"></i> ${category}
                            </h2>
                            <div style="flex: 1; height: 2px; background: var(--gradient); border-radius: 1px;"></div>
                        </div>
                        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 1.5rem;">
                            ${categoryArticles.map(article => createArticleCard(article)).join('')}
                        </div>
                    </div>
                `;
            });

            if (htmlContent === '') {
                grid.innerHTML = `
                    <div style="grid-column: 1/-1; text-align: center; padding: 3rem;">
                        <i class="fas fa-inbox" style="font-size: 4rem; color: var(--text-muted); margin-bottom: 1rem;"></i>
                        <h3>No articles found</h3>
                        <p style="color: var(--text-muted);">Try adjusting your filters</p>
                    </div>
                `;
            } else {
                grid.innerHTML = htmlContent;
            }
        }

        // Get Category Icon
        function getCategoryIcon(category) {
            const icons = {
                'World': 'globe',
                'Politics': 'landmark',
                'Business': 'briefcase',
                'Sports': 'football-ball'
            };
            return icons[category] || 'newspaper';
        }

        // Create Article Card
        function createArticleCard(article) {
            const publishedDate = new Date(article.published);
            const timeAgo = getTimeAgo(publishedDate);
            const imageUrl = article.image || 'https://via.placeholder.com/400x200/1e293b/64748b?text=No+Image';
            
            const badges = [];
            if (article.trending_score > 80) badges.push('<span class="badge trending"><i class="fas fa-fire"></i> Trending</span>');
            if (article.tier === 'premium') badges.push('<span class="badge premium"><i class="fas fa-crown"></i> Premium</span>');

            return `
                <div class="news-card" onclick='openArticle(${JSON.stringify(article).replace(/'/g, "&apos;")})'>
                    <div class="news-card-image">
                        <img src="${imageUrl}" alt="${article.title}" onerror="this.src='https://via.placeholder.com/400x200/1e293b/64748b?text=No+Image'">
                        <div class="news-card-badges">
                            ${badges.join('')}
                        </div>
                    </div>
                    <div class="news-card-content">
                        <div class="news-card-meta">
                            <div class="news-source">
                                <span class="source-logo">${article.source_logo}</span>
                                <span>${article.source}</span>
                            </div>
                            <span>${timeAgo}</span>
                        </div>
                        <h3 class="news-card-title">${article.title}</h3>
                        <p class="news-card-snippet">${article.snippet || 'No description available.'}</p>
                        <div class="news-card-footer">
                            <span class="sentiment-badge sentiment-${article.sentiment}">
                                <i class="fas fa-${getSentimentIcon(article.sentiment)}"></i>
                                ${article.sentiment}
                            </span>
                            <div class="news-actions">
                                <button class="action-btn" onclick="event.stopPropagation(); bookmarkArticle('${article.id}')" title="Bookmark">
                                    <i class="fas fa-bookmark"></i>
                                </button>
                                <button class="action-btn" onclick="event.stopPropagation(); shareArticle('${article.link}')" title="Share">
                                    <i class="fas fa-share-alt"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }

        // Open Article Modal
        function openArticle(article) {
            const modal = document.getElementById('articleModal');
            const modalBody = document.getElementById('modalBody');
            const imageUrl = article.image || 'https://via.placeholder.com/800x300/1e293b/64748b?text=No+Image';
            
            modalBody.innerHTML = `
                <img src="${imageUrl}" alt="${article.title}" class="modal-image" onerror="this.style.display='none'">
                <div style="margin-bottom: 1rem;">
                    <span class="badge ${article.tier}">${article.tier}</span>
                    <span class="sentiment-badge sentiment-${article.sentiment}" style="margin-left: 0.5rem;">
                        ${article.sentiment}
                    </span>
                </div>
                <h2 style="font-size: 1.8rem; margin-bottom: 1rem; line-height: 1.4;">${article.title}</h2>
                <div style="display: flex; gap: 1rem; margin-bottom: 1.5rem; color: var(--text-muted); font-size: 0.9rem;">
                    <div><i class="fas fa-newspaper"></i> ${article.source}</div>
                    <div><i class="fas fa-clock"></i> ${getTimeAgo(new Date(article.published))}</div>
                    <div><i class="fas fa-tag"></i> ${article.category}</div>
                </div>
                <p style="line-height: 1.8; margin-bottom: 2rem; color: var(--text);">${article.snippet}</p>
                <a href="${article.link}" target="_blank" class="btn btn-primary" style="display: inline-flex; text-decoration: none;">
                    <i class="fas fa-external-link-alt"></i> Read Full Article
                </a>
            `;
            
            modal.classList.add('active');
            document.body.style.overflow = 'hidden';
        }

        // Close Modal
        function closeModal() {
            const modal = document.getElementById('articleModal');
            modal.classList.remove('active');
            document.body.style.overflow = 'auto';
        }

        // Load More Articles
        function loadMore() {
            currentPage++;
            renderArticles();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        // Set View Mode
        function setView(view) {
            currentView = view;
            const grid = document.getElementById('newsGrid');
            const buttons = document.querySelectorAll('.view-btn');
            
            buttons.forEach(btn => btn.classList.remove('active'));
            event.target.closest('.view-btn').classList.add('active');
            
            if (view === 'list') {
                grid.classList.add('list-view');
            } else {
                grid.classList.remove('list-view');
            }
        }

        // Refresh News
        async function refreshNews() {
            try {
                const refreshIcon = document.getElementById('refreshIcon');
                refreshIcon.style.animation = 'spin 1s linear infinite';
                
                // Reset all filters to default
                document.querySelector('.nav-item[data-category="home"]').click();
                document.getElementById('sentimentFilter').value = '';
                document.getElementById('tierFilter').value = '';
                document.getElementById('sortFilter').value = 'date';
                
                await fetch('/api/refresh');
                await fetchNews();
                
                refreshIcon.style.animation = '';
                showNotification('News refreshed successfully!', 'success');
            } catch (error) {
                console.error('Error refreshing:', error);
                document.getElementById('refreshIcon').style.animation = '';
                showNotification('Failed to refresh news', 'error');
            }
        }

        // Bookmark Article
        function bookmarkArticle(id) {
            const article = allArticles.find(a => a.id === id);
            if (article) {
                showNotification(`Bookmarked: ${article.title.substring(0, 50)}...`, 'success');
            }
        }

        // Share Article
        function shareArticle(link) {
            if (navigator.share) {
                navigator.share({ url: link }).catch(() => {});
            } else {
                navigator.clipboard.writeText(link);
                showNotification('Link copied to clipboard!', 'success');
            }
        }

        // Scroll to Top
        function scrollToTop() {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        // Helper Functions
        function getTimeAgo(date) {
            const seconds = Math.floor((new Date() - date) / 1000);
            const intervals = {
                year: 31536000,
                month: 2592000,
                week: 604800,
                day: 86400,
                hour: 3600,
                minute: 60
            };

            for (const [unit, secondsInUnit] of Object.entries(intervals)) {
                const interval = Math.floor(seconds / secondsInUnit);
                if (interval >= 1) {
                    return `${interval} ${unit}${interval > 1 ? 's' : ''} ago`;
                }
            }
            return 'Just now';
        }

        function getSentimentIcon(sentiment) {
            const icons = {
                positive: 'smile',
                negative: 'frown',
                neutral: 'meh'
            };
            return icons[sentiment] || 'meh';
        }

        function showLoading() {
            document.getElementById('newsGrid').innerHTML = `
                <div class="loading" style="grid-column: 1/-1;">
                    <div class="spinner"></div>
                    <p>Loading amazing news for you...</p>
                </div>
            `;
        }

        function hideLoading() {
            // Loading is replaced by articles
        }

        function showError(message) {
            document.getElementById('newsGrid').innerHTML = `
                <div style="grid-column: 1/-1; text-align: center; padding: 3rem;">
                    <i class="fas fa-exclamation-triangle" style="font-size: 4rem; color: var(--danger); margin-bottom: 1rem;"></i>
                    <h3>Oops! Something went wrong</h3>
                    <p style="color: var(--text-muted); margin: 1rem 0;">${message}</p>
                    <button class="btn btn-primary" onclick="fetchNews()">
                        <i class="fas fa-redo"></i> Try Again
                    </button>
                </div>
            `;
        }

        function showNotification(message, type = 'info') {
            const notification = document.createElement('div');
            notification.style.cssText = `
                position: fixed;
                top: 100px;
                right: 2rem;
                background: ${type === 'success' ? 'var(--secondary)' : type === 'error' ? 'var(--danger)' : 'var(--primary)'};
                color: white;
                padding: 1rem 1.5rem;
                border-radius: 8px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                z-index: 3000;
                animation: slideIn 0.3s ease;
                max-width: 300px;
            `;
            notification.innerHTML = `<i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i> ${message}`;
            document.body.appendChild(notification);
            
            setTimeout(() => {
                notification.style.animation = 'slideOut 0.3s ease';
                setTimeout(() => notification.remove(), 300);
            }, 3000);
        }

        // Close modal on outside click
        document.getElementById('articleModal').addEventListener('click', (e) => {
            if (e.target.id === 'articleModal') closeModal();
        });

        // Add animations
        const style = document.createElement('style');
        style.textContent = `
            @keyframes slideIn {
                from { transform: translateX(400px); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes slideOut {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(400px); opacity: 0; }
            }
        `;
        document.head.appendChild(style);