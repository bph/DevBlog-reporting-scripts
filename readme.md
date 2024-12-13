## Devblog Reports

### WordPress REST API Fetcher

This script fetches posts from the WordPress REST API and generates a Markdown report based on the views data from Jetpack csv download.
#### Usage

1. Download the Jetpack csv file from the WordPress dashboard.
2. Run the script: `python wordpress-rest-api-fetcher.py`
3. Follow the prompts to input the date filter and view the report.

#### Requirements

- Python 3.x
- `requests` library
- `python-dotenv` library

