const axios = require('axios');
const { parse } = require('csv-parse/sync');
const fs = require('fs').promises;

// Constants
const BASE_URL = 'https://developer.wordpress.org/news';
const POST_TYPES = ['snippets', 'dev-blog-videos', 'posts'];
const DATE_FORMATS = [
    'YYYY-MM-DD',    // YYYY-MM-DD
    'MM/DD/YYYY',    // MM/DD/YYYY
    'DD-MM-YYYY',    // DD-MM-YYYY
    'YYYY/MM/DD',    // YYYY/MM/DD
];

/**
 * Parse date string in various formats
 * @param {string} dateStr - Date string to parse
 * @returns {Date} Parsed date object
 */
function parseDateInput(dateStr) {
    const date = new Date(dateStr);
    if (!isNaN(date)) {
        return date;
    }
    throw new Error(`Unable to parse date: ${dateStr}. Please use format YYYY-MM-DD`);
}

/**
 * Normalize URL by handling various date formats
 * @param {string} url - URL to normalize
 * @returns {string} Normalized URL
 */
function normalizeUrl(url) {
    const urlLower = url.toLowerCase().replace(/\/$/, '');
    const parts = urlLower.split('/');
    const normalized = [];
    
    for (let i = 0; i < parts.length; i++) {
        const part = parts[i];
        // If we find a year (4 digits)
        if (/^\d{4}$/.test(part)) {
            normalized.push(part);
            // Check for month
            if (i + 1 < parts.length && /^\d{1,2}$/.test(parts[i + 1])) {
                normalized.push(parts[i + 1]);
                // Skip day if present
                if (i + 2 < parts.length && /^\d{1,2}$/.test(parts[i + 2])) {
                    i += 2;
                } else {
                    i += 1;
                }
                continue;
            }
        }
        normalized.push(part);
    }
    
    return normalized.join('/');
}

/**
 * Convert CSV content to JSON format
 * @param {string} csvContent - Raw CSV content
 * @returns {Object} Parsed views data
 */
function csvToJson(csvContent) {
    const records = parse(csvContent, {
        columns: false,
        skip_empty_lines: true
    });
    
    const viewsData = {};
    let processed = 0;
    let skipped = 0;

    for (const [title, views, url] of records) {
        try {
            const cleanUrl = url.replace(/^"|"$/g, '').replace(/\/$/, '');
            viewsData[cleanUrl] = {
                title: title.replace(/^"|"$/g, ''),
                views: parseInt(views, 10)
            };
            processed++;
        } catch (error) {
            console.debug(`Skipped line: ${error.message}`);
            skipped++;
        }
    }

    console.log(`Processed ${processed} lines, skipped ${skipped} lines`);
    return viewsData;
}

/**
 * Fetch posts from WordPress REST API
 * @param {Object} options - Fetch options
 * @returns {Promise<Array>} List of formatted posts
 */
async function fetchWordPressPosts({ 
    baseUrl, 
    postTypes, 
    afterDate = null, 
    page = 1, 
    perPage = 100, 
    viewsData = {} 
}) {
    const allPosts = [];

    for (const postType of postTypes) {
        try {
            const params = {
                page,
                per_page: perPage,
                _embed: 'true'
            };

            if (afterDate) {
                params.after = afterDate.toISOString();
            }

            const response = await axios.get(
                `${baseUrl}/wp-json/wp/v2/${postType}`,
                { params }
            );

            for (const post of response.data) {
                const postUrl = post.link;
                const normalizedPostUrl = normalizeUrl(postUrl);
                
                // Find matching URL in views data
                const matchedUrl = Object.keys(viewsData)
                    .find(url => normalizeUrl(url) === normalizedPostUrl);

                const views = matchedUrl ? viewsData[matchedUrl].views : 0;
                
                allPosts.push({
                    id: post.id,
                    title: post.title.rendered,
                    publication_date: new Date(post.date).toISOString().split('T')[0],
                    author: post._embedded?.author?.[0]?.name || 'Unknown',
                    url: postUrl,
                    type: postType,
                    views
                });
            }
        } catch (error) {
            console.error(`Error fetching ${postType}:`, error.message);
        }
    }

    return allPosts;
}

/**
 * Generate markdown output
 * @param {Array} posts - List of posts
 * @param {string} inputDate - Date string for header
 * @returns {string} Markdown formatted string
 */
function generateMarkdownOutput(posts, inputDate) {
    const markdown = [
        '# Dev Blog News',
        `## Posts Published After ${inputDate}`,
        '',
        '| Date | Title | Author | Type | Views | Post ID |',
        '|------|-------|--------|------|-------|----------|'
    ];

    // Sort posts by publication date (ascending)
    const sortedPosts = posts.sort((a, b) => 
        a.publication_date.localeCompare(b.publication_date)
    );

    for (const post of sortedPosts) {
        const safeTitle = `[${post.title.replace(/\|/g, '&#124;')}](${post.url})`;
        markdown.push(
            `| ${post.publication_date} | ${safeTitle} | ${post.author} | ${post.type} | ${post.views} | ${post.id} |`
        );
    }

    return markdown.join('\n');
}

/**
 * Main execution function
 */
async function main() {
    try {
        // Load views data from CSV
        const csvContent = await fs.readFile(
            'developer.wordpress.org__news-posts-week-09_30_2024-10_06_2024.csv',
            'utf-8'
        );
        const viewsData = csvToJson(csvContent);

        // Save as JSON for future use
        await fs.writeFile(
            'views_data.json',
            JSON.stringify(viewsData, null, 2)
        );
        console.log('Views data loaded and converted to JSON successfully');

        // Get date input
        const dateInput = process.argv[2] || '';
        let afterDate = null;

        if (dateInput) {
            try {
                afterDate = parseDateInput(dateInput);
            } catch (error) {
                console.error(`Error: ${error.message}`);
                process.exit(1);
            }
        }

        // Fetch posts
        const posts = await fetchWordPressPosts({
            baseUrl: BASE_URL,
            postTypes: POST_TYPES,
            afterDate,
            viewsData
        });

        if (posts.length > 0) {
            const markdown = generateMarkdownOutput(posts, dateInput || 'all');
            const safeFilename = `devblognews-${dateInput || 'all'}`
                .replace(/[^a-z0-9-_]/gi, '');
            
            await fs.writeFile(`${safeFilename}.md`, markdown);
            
            console.log(`\nFound ${posts.length} posts published after ${dateInput || 'any date'}.`);
            console.log(`Markdown output saved to: ${safeFilename}.md`);
        } else {
            console.log('No posts found.');
        }

    } catch (error) {
        console.error('Error:', error.message);
        process.exit(1);
    }
}

// Run the script
main(); 