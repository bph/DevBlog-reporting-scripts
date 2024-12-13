import requests
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
BASE_URL = 'https://developer.wordpress.org/news'
POST_TYPES = ['snippets', 'dev-blog-videos', 'posts']
DATE_FORMATS = [
    '%Y-%m-%d',    # YYYY-MM-DD
    '%m/%d/%Y',    # MM/DD/YYYY
    '%d-%m-%Y',    # DD-MM-YYYY
    '%Y/%m/%d',    # YYYY/MM/DD
    '%B %d, %Y',   # Full month name
    '%b %d, %Y'    # Abbreviated month name
]

def parse_date_input(date_str: str) -> datetime:
    """
    Parse user-input date in various common formats.
    
    Args:
        date_str: Date string in formats like YYYY-MM-DD, MM/DD/YYYY, etc.
    
    Returns:
        datetime object
    
    Raises:
        ValueError: If the date string cannot be parsed
    """
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    raise ValueError(f"Unable to parse date: {date_str}. Please use formats like YYYY-MM-DD or MM/DD/YYYY")

def normalize_url(url: str) -> str:
    """
    Normalize URL for comparison by handling various date formats.
    
    Example:
        Input:  https://developer.wordpress.org/news/2024/12/10/post-title/
        Output: https://developer.wordpress.org/news/2024/12/post-title
    
    Args:
        url: URL to normalize
    
    Returns:
        Normalized URL string
    """
    url = url.lower().rstrip('/')
    parts = url.split('/')
    normalized_parts = []
    i = 0
    
    while i < len(parts):
        part = parts[i]
        if part.isdigit() and len(part) == 4:  # Year
            normalized_parts.append(part)
            if i + 1 < len(parts) and parts[i + 1].isdigit() and len(parts[i + 1]) <= 2:  # Month
                normalized_parts.append(parts[i + 1])
                if i + 2 < len(parts) and parts[i + 2].isdigit() and len(parts[i + 2]) <= 2:  # Day
                    i += 3
                else:
                    i += 2
                continue
        normalized_parts.append(part)
        i += 1
    
    return '/'.join(normalized_parts)

def csv_to_json(csv_content: str) -> Dict[str, Dict[str, Any]]:
    """
    Convert CSV content to JSON format with URL as key and views as value.
    
    Args:
        csv_content: Raw CSV content string
    
    Returns:
        Dictionary with URLs as keys and post data as values
    """
    views_data = {}
    skipped_lines = 0
    processed_lines = 0
    
    for line in csv_content.strip().split('\n'):
        try:
            # Handle quoted strings containing commas
            if line.startswith('"'):
                # Find the end of the title (next quote followed by comma)
                title_end = line.find('",', 1)
                if title_end == -1:
                    raise ValueError("Malformed CSV line: missing closing quote for title")
                
                title = line[1:title_end]  # Remove surrounding quotes
                remainder = line[title_end + 2:]  # Skip quote and comma
                
                # Split the remainder into views and URL
                views_str, url = remainder.split(',', 1)
            else:
                # Simple case without quotes
                title_part, views_str, url = line.split(',', 2)
                title = title_part
            
            # Clean up the values
            url = url.strip().strip('"').rstrip('/')
            views = int(views_str.strip())
            
            views_data[url] = {
                'title': title,
                'views': views
            }
            processed_lines += 1
            
        except (ValueError, IndexError) as e:
            skipped_lines += 1
            logger.debug(f"Skipped line: {line.strip()}")  # Changed to debug level
            continue
    
    logger.info(f"Processed {processed_lines} lines, skipped {skipped_lines} lines")
    return views_data

def fetch_wordpress_posts(
    base_url: str,
    post_types: List[str],
    after_date: Optional[datetime] = None,
    page: int = 1,
    per_page: int = 100,
    views_data: Optional[Dict] = None
) -> List[Dict]:
    """
    Fetch posts from WordPress REST API with type and date filtering.
    
    Args:
        base_url: Base URL for the WordPress site
        post_types: List of post types to fetch
        after_date: Only fetch posts after this date
        page: Page number for pagination
        per_page: Number of posts per page
        views_data: Dictionary containing view counts
    
    Returns:
        List of formatted post dictionaries
    """
    if views_data is None:
        views_data = {}
        
    all_posts = []
    
    for post_type in post_types:
        params = {
            'page': page,
            'per_page': per_page,
            '_embed': 'true'
        }
        
        if after_date:
            params['after'] = after_date.isoformat()
            
        try:
            response = requests.get(
                f"{base_url}/wp-json/wp/v2/{post_type}",
                params=params
            )
            response.raise_for_status()
            posts = response.json()
            
            for post in posts:
                post_url = post['link']
                normalized_post_url = normalize_url(post_url)
                
                # Find matching URL in views data
                matched_url = next(
                    (url for url in views_data.keys() 
                     if normalize_url(url) == normalized_post_url),
                    None
                )
                
                all_posts.append({
                    'id': post['id'],
                    'title': post['title']['rendered'],
                    'publication_date': datetime.fromisoformat(post['date'].replace('Z', '+00:00')).strftime('%Y-%m-%d'),
                    'author': post.get('_embedded', {}).get('author', [{'name': 'Unknown'}])[0]['name'],
                    'url': post_url,
                    'type': post_type,
                    'views': views_data.get(matched_url, {}).get('views', 0)
                })
                
        except requests.RequestException as e:
            logger.error(f"Error fetching {post_type}: {e}")
            continue
    
    return all_posts

def generate_markdown_output(posts: List[Dict], input_date: str) -> str:
    """
    Generate a Markdown-formatted string of posts.
    
    Args:
        posts: List of post dictionaries
        input_date: Date string used for the header
    
    Returns:
        Markdown formatted string
    """
    markdown_lines = [
        "# Dev Blog News",
        f"## Posts Published After {input_date}",
        "",
        "| Date | Title | Author | Type | Views | Post ID |",
        "|------|-------|--------|------|-------|----------|"
    ]
    
    # Sort posts by publication date (ascending)
    sorted_posts = sorted(posts, key=lambda x: x['publication_date'])
    
    for post in sorted_posts:
        safe_title = f"[{post['title'].replace('|', '&#124;')}]({post['url']})"
        markdown_lines.append(
            f"| {post['publication_date']} | {safe_title} | {post['author']} | {post['type']} | {post['views']} | {post['id']} |"
        )
    
    return "\n".join(markdown_lines)

def main():
    """Main execution function."""
    # Load views data from CSV
    try:
        with open('developer.wordpress.org__news-posts-week-09_30_2024-10_06_2024.csv', 'r') as file:
            views_data = csv_to_json(file.read())
            
            # Save as JSON file for future use
            with open('views_data.json', 'w') as json_file:
                json.dump(views_data, json_file, indent=2)
            logger.info("Views data loaded and converted to JSON successfully")
            
    except FileNotFoundError:
        views_data = {}
        logger.warning("Views data file not found")
    
    # Prompt user for date filter
    while True:
        try:
            date_input = input("Enter the date to fetch posts published after (YYYY-MM-DD): ").strip()
            
            if not date_input:
                after_date = None
                date_input = 'all'
                break
            
            after_date = parse_date_input(date_input)
            break
        except ValueError as e:
            logger.error(f"Error: {e}")
            print("Please try again.")
    
    # Fetch posts
    posts = fetch_wordpress_posts(
        base_url=BASE_URL,
        post_types=POST_TYPES,
        after_date=after_date,
        views_data=views_data
    )
    
    # Generate output
    if posts:
        markdown_content = generate_markdown_output(posts, date_input)
        safe_filename = ''.join(c if c.isalnum() or c in ['-', '_'] else '' for c in f"devblognews-{date_input}")
        output_filename = f"{safe_filename}.md"
        
        try:
            with open(output_filename, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            logger.info(f"\nFound {len(posts)} posts published after {date_input if date_input != 'all' else 'any date'}.")
            logger.info(f"Markdown output saved to: {output_filename}")
        
        except IOError as e:
            logger.error(f"Error writing to file: {e}")
    else:
        logger.warning("No posts found.")

if __name__ == '__main__':
    main() 