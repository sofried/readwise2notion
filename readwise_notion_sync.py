#!/usr/bin/env python3
"""
Readwise to Notion Sync Script
Automatically syncs highlights from Readwise to Notion
Only processes items (books, articles, podcasts, etc.) with new highlights since last sync

Usage:
    python readwise_notion_sync.py              # Normal sync (since last sync)
    python readwise_notion_sync.py --days 7     # Sync last 7 days
    python readwise_notion_sync.py --days 30    # Sync last 30 days
    python readwise_notion_sync.py --all        # Sync everything (ignore last sync time)
"""

import os
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
from pathlib import Path
import argparse

# Configuration - reads from environment variables (for GitHub Actions)
# If running locally, you can hardcode your tokens here instead
READWISE_API_TOKEN = os.getenv('READWISE_TOKEN', 'YOUR_READWISE_TOKEN_HERE')
NOTION_API_TOKEN = os.getenv('NOTION_TOKEN', 'YOUR_NOTION_TOKEN_HERE')
NOTION_DATABASE_ID = os.getenv('NOTION_DATABASE_ID', 'YOUR_DATABASE_ID_HERE')

# OPTIONAL: Sync only highlights from the last N days (set to None for all time)
# Example: DAYS_TO_SYNC = 7 will only sync highlights from the last 7 days
# Set to None or 0 to sync all highlights regardless of date
DAYS_TO_SYNC = os.getenv('DAYS_TO_SYNC', None)
if DAYS_TO_SYNC:
    try:
        DAYS_TO_SYNC = int(DAYS_TO_SYNC)
    except:
        DAYS_TO_SYNC = None

READWISE_API_BASE = "https://readwise.io/api/v2"
NOTION_API_BASE = "https://api.notion.com/v1"

# File to track last sync time
LAST_SYNC_FILE = Path(__file__).parent / ".last_sync_time.json"

# File to track items that have been synced (so we don't recreate deleted ones)
SYNCED_ITEMS_FILE = Path(__file__).parent / ".synced_items.json"

# Category mapping from Readwise to your Notion categories
CATEGORY_MAP = {
    "books": "Books",
    "articles": "Articles",
    "tweets": "Quote",
    "podcasts": "Podcast",
    "supplementals": "Articles"
}


class ReadwiseNotionSync:
    def __init__(self):
        self.readwise_headers = {
            "Authorization": f"Token {READWISE_API_TOKEN}"
        }
        self.notion_headers = {
            "Authorization": f"Bearer {NOTION_API_TOKEN}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        self.last_sync_time = self.load_last_sync_time()
        self.synced_items = self.load_synced_items()
    
    def load_synced_items(self) -> set:
        """Load the set of Readwise IDs that have been synced before"""
        if SYNCED_ITEMS_FILE.exists():
            try:
                with open(SYNCED_ITEMS_FILE, 'r') as f:
                    data = json.load(f)
                    return set(data.get('synced_ids', []))
            except:
                pass
        return set()
    
    def save_synced_items(self, readwise_ids: list):
        """Save the list of Readwise IDs that have been synced"""
        # Add new IDs to existing set
        self.synced_items.update(readwise_ids)
        
        with open(SYNCED_ITEMS_FILE, 'w') as f:
            json.dump({'synced_ids': list(self.synced_items)}, f)
        print(f"💾 Tracked {len(self.synced_items)} total synced items")
    
    def load_last_sync_time(self) -> Optional[str]:
        """Load the timestamp of the last successful sync"""
        if LAST_SYNC_FILE.exists():
            try:
                with open(LAST_SYNC_FILE, 'r') as f:
                    data = json.load(f)
                    last_time = data.get('last_sync_time')
                    if last_time:
                        print(f"📅 Last sync was: {last_time}")
                    return last_time
            except:
                pass
        print("📅 No previous sync found - will sync all items")
        return None
    
    def save_last_sync_time(self):
        """Save the current time as the last sync time"""
        current_time = datetime.utcnow().isoformat() + 'Z'
        with open(LAST_SYNC_FILE, 'w') as f:
            json.dump({'last_sync_time': current_time}, f)
        print(f"💾 Saved last sync time: {current_time}")
    
    def get_readwise_books(self, updated_after: Optional[str] = None) -> List[Dict]:
        """
        Fetch items from Readwise (books, articles, podcasts, tweets, etc.)
        Readwise API calls everything a 'book' but includes all content types
        """
        url = f"{READWISE_API_BASE}/books/"
        params = {}
        
        # Only get items with highlights created after this date
        if updated_after:
            # Format date properly for Readwise API (remove microseconds)
            if '.' in updated_after:
                updated_after = updated_after.split('.')[0] + 'Z'
            
            params['highlighted_after'] = updated_after
            print(f"🔍 Fetching only items with highlights created since {updated_after}")
        
        all_books = []
        
        while url:
            response = requests.get(url, params=params, headers=self.readwise_headers)
            response.raise_for_status()
            data = response.json()
            
            all_books.extend(data.get('results', []))
            url = data.get('next')  # Pagination
            params = {}  # Clear params for subsequent pages
        
        # BACKUP: Client-side filter if API filter didn't work properly
        if updated_after and all_books:
            print(f"   📊 API returned {len(all_books)} items")
            # Filter by last_highlight_at on client side as backup
            filtered_books = []
            cutoff_date = updated_after.replace('Z', '')  # Remove Z for comparison
            
            for book in all_books:
                last_highlight = book.get('last_highlight_at', '')
                if last_highlight:
                    # Remove Z and compare
                    highlight_date = last_highlight.replace('Z', '')
                    if highlight_date >= cutoff_date:
                        filtered_books.append(book)
            
            if len(filtered_books) < len(all_books):
                print(f"   🔍 Client-side filter: {len(filtered_books)} items actually match date range")
                all_books = filtered_books
        
        return all_books
    
    def search_notion_page(self, title: str) -> Optional[Dict]:
        """Check if a page with this title already exists in Library"""
        url = f"{NOTION_API_BASE}/databases/{NOTION_DATABASE_ID}/query"
        
        payload = {
            "filter": {
                "property": "Title",
                "title": {
                    "equals": title
                }
            }
        }
        
        response = requests.post(url, headers=self.notion_headers, json=payload)
        response.raise_for_status()
        
        results = response.json().get('results', [])
        return results[0] if results else None
    
    def batch_search_notion_pages(self, titles: List[str]) -> Dict[str, Dict]:
        """
        Search for multiple pages at once (much more efficient!)
        Returns a dictionary mapping title -> page object
        """
        if not titles:
            return {}
        
        # Notion has limits on filter complexity, so batch in groups of 100
        MAX_BATCH_SIZE = 100
        all_pages = {}
        
        for i in range(0, len(titles), MAX_BATCH_SIZE):
            batch_titles = titles[i:i+MAX_BATCH_SIZE]
            
            url = f"{NOTION_API_BASE}/databases/{NOTION_DATABASE_ID}/query"
            
            # Build OR filter for all titles in this batch
            if len(batch_titles) == 1:
                filter_obj = {
                    "property": "Title",
                    "title": {
                        "equals": batch_titles[0]
                    }
                }
            else:
                filter_obj = {
                    "or": [
                        {
                            "property": "Title",
                            "title": {
                                "equals": title
                            }
                        }
                        for title in batch_titles
                    ]
                }
            
            payload = {"filter": filter_obj}
            
            response = requests.post(url, headers=self.notion_headers, json=payload)
            
            # Print detailed error if it fails
            if not response.ok:
                print(f"\n⚠️  Notion API Error:")
                print(f"   Status: {response.status_code}")
                print(f"   Response: {response.text}")
                print(f"   Searching for {len(batch_titles)} titles (batch {i//MAX_BATCH_SIZE + 1})")
            
            response.raise_for_status()
            
            results = response.json().get('results', [])
            
            # Build a map of title -> page for easy lookup
            for page in results:
                # Extract title from the page
                title_prop = page.get('properties', {}).get('Title', {})
                if title_prop.get('title'):
                    page_title = title_prop['title'][0]['plain_text']
                    all_pages[page_title] = page
        
        return all_pages
    
    def get_highlights_for_book(self, book_id: int, updated_after: Optional[str] = None) -> List[Dict]:
        """
        Get highlights for a specific book
        If updated_after is provided, only return highlights created after that date
        """
        url = f"{READWISE_API_BASE}/highlights/"
        params = {"book_id": book_id}
        
        # Add date filter if specified (use highlighted_after to filter by creation date)
        if updated_after:
            params['highlighted_after'] = updated_after
        
        response = requests.get(url, params=params, headers=self.readwise_headers)
        response.raise_for_status()
        
        return response.json().get('results', [])
    
    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison by removing formatting, whitespace, and standardizing"""
        import re
        # Remove markdown bold/italic formatting
        text = re.sub(r'\*\*', '', text)
        text = re.sub(r'\*', '', text)
        text = re.sub(r'__', '', text)
        text = re.sub(r'_', '', text)
        # Remove extra whitespace, newlines, and lowercase
        text = re.sub(r'\s+', ' ', text.strip())
        return text.lower()
    
    def get_existing_page_content(self, page_id: str) -> set:
        """Get the first 1000 chars of each existing highlight as fingerprints"""
        url = f"{NOTION_API_BASE}/blocks/{page_id}/children"
        
        existing_fingerprints = set()
        has_more = True
        start_cursor = None
        
        while has_more:
            params = {}
            if start_cursor:
                params['start_cursor'] = start_cursor
            
            response = requests.get(url, params=params, headers=self.notion_headers)
            response.raise_for_status()
            data = response.json()
            
            # Extract first 1000 chars from QUOTE blocks as fingerprints
            for block in data.get('results', []):
                block_type = block.get('type')
                if block_type == 'quote':
                    text = ''.join([t.get('plain_text', '') for t in block.get('quote', {}).get('rich_text', [])])
                    if text:
                        # Use first 1000 chars as fingerprint
                        fingerprint = self.normalize_text(text[:1000])
                        existing_fingerprints.add(fingerprint)
            
            has_more = data.get('has_more', False)
            start_cursor = data.get('next_cursor')
        
        return existing_fingerprints
    
    def append_highlights_to_page(self, page_id: str, highlights: List[Dict]):
        """Append only NEW highlights to the Notion page (skip ones already there)"""
        
        # Sort highlights by creation date (oldest first, so newest end up at bottom)
        # Readwise returns highlights with 'highlighted_at' timestamp
        highlights_sorted = sorted(highlights, key=lambda h: h.get('highlighted_at', ''))
        
        # Get fingerprints of existing highlights
        existing_fingerprints = self.get_existing_page_content(page_id)
        
        url = f"{NOTION_API_BASE}/blocks/{page_id}/children"
        
        # Build blocks for NEW highlights only
        blocks = []
        new_count = 0
        skipped_count = 0
        
        print(f"      🔍 Found {len(existing_fingerprints)} existing highlights on page")
        
        for highlight in highlights_sorted:
            highlight_text = highlight.get('text', '')
            
            # Create fingerprint from first 1000 chars
            fingerprint = self.normalize_text(highlight_text[:1000])
            
            # Check if this highlight already exists
            if fingerprint in existing_fingerprints:
                skipped_count += 1
                continue
            
            # Add clean quote block (no visible ID!)
            blocks.append({
                "object": "block",
                "type": "quote",
                "quote": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": highlight_text[:2000]}
                    }],
                    "color": "default"
                }
            })
            new_count += 1
            
            # Add note if exists
            if highlight.get('note'):
                blocks.append({
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "rich_text": [{
                            "type": "text",
                            "text": {"content": f"Note: {highlight.get('note')[:2000]}"}
                        }],
                        "icon": {"emoji": "💭"},
                        "color": "gray_background"
                    }
                })
        
        if new_count == 0:
            print(f"      ℹ️  All {len(highlights)} highlights already exist (skipped)")
            return
        
        print(f"      ✅ Adding {new_count} new highlights ({skipped_count} already exist)")
        print(f"      📍 Highlights are in chronological order (oldest → newest)")
        
        # Notion allows max 100 blocks per request
        for i in range(0, len(blocks), 100):
            chunk = blocks[i:i+100]
            payload = {"children": chunk}
            
            response = requests.patch(url, headers=self.notion_headers, json=payload)
            response.raise_for_status()
    
    def create_notion_page(self, book: Dict) -> Dict:
        """Create a new page in Notion Library database"""
        url = f"{NOTION_API_BASE}/pages"
        
        # Map Readwise category to your Notion category
        readwise_category = book.get('category', 'books').lower()
        category = CATEGORY_MAP.get(readwise_category, 'Books')
        
        # Get current timestamp for Last Synced
        current_time = datetime.utcnow().isoformat()
        
        # Build page properties
        properties = {
            "Title": {
                "title": [{"text": {"content": book.get('title', 'Untitled')}}]
            },
            "Author": {
                "rich_text": [{"text": {"content": book.get('author', '')}}]
            },
            "Category": {
                "select": {"name": category}
            },
            "Highlights": {
                "number": book.get('num_highlights', 0)
            },
            "Status": {
                "status": {"name": "Not started"}
            },
            "Last Synced": {
                "date": {
                    "start": current_time,
                    "time_zone": None
                }
            }
        }
        
        # Add Readwise URL to your URL field
        book_id = book.get('id')
        if book_id:
            properties["URL"] = {
                "url": f"https://readwise.io/bookreview/{book_id}"
            }
        
        # Add Last Highlighted date if available
        if book.get('last_highlight_at'):
            properties["Last Highlighted"] = {
                "date": {
                    "start": book.get('last_highlight_at'),
                    "time_zone": None
                }
            }
        
        payload = {
            "parent": {"database_id": NOTION_DATABASE_ID},
            "properties": properties
        }
        
        # Add cover image if available
        cover_url = book.get('cover_image_url')
        if cover_url:
            payload["cover"] = {
                "type": "external",
                "external": {"url": cover_url}
            }
            # Also set as icon
            payload["icon"] = {
                "type": "external",
                "external": {"url": cover_url}
            }
        
        response = requests.post(url, headers=self.notion_headers, json=payload)
        
        # Print detailed error if it fails
        if not response.ok:
            print(f"\n⚠️  Error creating page:")
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text}")
            print(f"   Book data: {book.get('title')} - Category: {category}")
        
        response.raise_for_status()
        
        return response.json()
    
    def update_notion_page(self, page_id: str, book: Dict):
        """Update existing Notion page with new highlight count and last synced"""
        url = f"{NOTION_API_BASE}/pages/{page_id}"
        
        # Get current timestamp for Last Synced
        current_time = datetime.utcnow().isoformat()
        
        # Build properties - using correct Notion date format
        properties = {
            "Highlights": {
                "number": book.get('num_highlights', 0)
            },
            "Last Synced": {
                "date": {
                    "start": current_time,
                    "time_zone": None
                }
            }
        }
        
        # Add Last Highlighted if available
        if book.get('last_highlight_at'):
            properties["Last Highlighted"] = {
                "date": {
                    "start": book.get('last_highlight_at'),
                    "time_zone": None
                }
            }
        
        payload = {"properties": properties}
        
        # Add cover image if available
        cover_url = book.get('cover_image_url')
        if cover_url:
            payload["cover"] = {
                "type": "external",
                "external": {"url": cover_url}
            }
            # Also set as icon
            payload["icon"] = {
                "type": "external",
                "external": {"url": cover_url}
            }
        
        response = requests.patch(url, headers=self.notion_headers, json=payload)
        
        # Print detailed error if it fails
        if not response.ok:
            print(f"\n⚠️  Error updating page:")
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text}")
        
        response.raise_for_status()
        
        return response.json()
    
    def full_sync(self):
        """
        Sync items from Readwise to Notion Library
        Only processes items (books, articles, podcasts, etc.) with new highlights since last sync
        """
        print("🚀 SMART SYNC: Only processing items with new highlights...\n")
        print("=" * 60)
        
        # Show tracking status
        print(f"📊 Tracking {len(self.synced_items)} previously synced items")
        
        # Get items updated since last sync (or all if first run)
        books = self.get_readwise_books(updated_after=self.last_sync_time)
        
        if len(books) == 0:
            print("✨ No new highlights since last sync!")
            print("=" * 60)
            return
        
        print(f"📚 Found {len(books)} items with new highlights")
        print(f"   (books, articles, podcasts, tweets, etc.)\n")
        print("=" * 60)
        
        # OPTIMIZATION 1: Batch search all titles at once instead of one-by-one
        print(f"\n🔍 Checking which items already exist in Notion...")
        all_titles = [book.get('title', 'Untitled') for book in books]
        existing_pages_map = self.batch_search_notion_pages(all_titles)
        print(f"   Found {len(existing_pages_map)} existing pages")
        
        created_count = 0
        updated_count = 0
        skipped_count = 0
        synced_ids = []  # Track IDs we process
        
        for i, book in enumerate(books, 1):
            title = book.get('title', 'Untitled')
            book_id = book.get('id')
            
            print(f"\n[{i}/{len(books)}] Processing: {title}")
            
            # Check if page exists using our pre-fetched map
            existing_page = existing_pages_map.get(title)
            
            # Check if this was synced before (even if page doesn't exist now)
            was_synced_before = book_id in self.synced_items
            
            if existing_page:
                print(f"   ✏️  Checking existing page...")
                
                # OPTIMIZATION 2: Only fetch highlights if count changed
                existing_highlight_count = existing_page.get('properties', {}).get('Highlights', {}).get('number', 0)
                new_highlight_count = book.get('num_highlights', 0)
                
                # Only fetch and append highlights if there are NEW ones
                if new_highlight_count > existing_highlight_count:
                    print(f"   📝 Found {new_highlight_count - existing_highlight_count} new highlights...")
                    # For existing pages: only fetch highlights created since last sync
                    # This protects manual deletions/edits in Notion
                    highlights = self.get_highlights_for_book(book['id'], updated_after=self.last_sync_time)
                    if highlights:
                        self.append_highlights_to_page(existing_page['id'], highlights)
                        # Update page metadata ONLY when highlights were actually added
                        self.update_notion_page(existing_page['id'], book)
                        updated_count += 1
                        synced_ids.append(book_id)  # Track this ID
                    else:
                        print(f"   ⚠️  Count increased but no new highlights found (might be a sync timing issue)")
                else:
                    print(f"   ℹ️  No new highlights (still {new_highlight_count} total)")
                    # Still track this ID even though we didn't update it
                    synced_ids.append(book_id)
            elif was_synced_before:
                # Item was synced before but page doesn't exist now (user deleted it)
                print(f"   🗑️  Previously synced (ID: {book_id}) but deleted from Notion - skipping")
                skipped_count += 1
                # Still track this ID so we remember it was processed
                synced_ids.append(book_id)
            else:
                # Brand new item - never synced before
                print(f"   ✨ Creating new page (ID: {book_id}, never synced before)...")
                new_page = self.create_notion_page(book)
                created_count += 1
                synced_ids.append(book_id)  # Track this ID
                
                # For NEW pages: get ALL highlights (not filtered by date)
                # This ensures first sync gets complete history
                if book.get('num_highlights', 0) > 0:
                    print(f"   📝 Adding all {book['num_highlights']} highlights...")
                    highlights = self.get_highlights_for_book(book['id'], updated_after=None)
                    self.append_highlights_to_page(new_page['id'], highlights)
        
        print("\n" + "=" * 60)
        print(f"✅ SYNC COMPLETE!")
        print(f"   Created: {created_count} new pages")
        print(f"   Updated: {updated_count} existing pages")
        if skipped_count > 0:
            print(f"   Skipped: {skipped_count} previously deleted items")
        print(f"   Total processed: {len(books)} items")
        
        # Save tracking data for next run
        self.save_synced_items(synced_ids)
        self.save_last_sync_time()


def main():
    """Run the full sync with optional command-line arguments"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Sync Readwise highlights to Notion',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python readwise_notion_sync.py              # Normal sync (since last sync)
  python readwise_notion_sync.py --days 7     # Sync last 7 days only
  python readwise_notion_sync.py --days 30    # Sync last 30 days only
  python readwise_notion_sync.py --all        # Sync everything (ignore last sync)
        """
    )
    parser.add_argument(
        '--days',
        type=int,
        metavar='N',
        help='Sync highlights from the last N days (overrides last sync time)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Sync all highlights (ignore last sync time)'
    )
    
    args = parser.parse_args()
    
    try:
        # Check if tokens are set
        if READWISE_API_TOKEN == 'YOUR_READWISE_TOKEN_HERE':
            print("❌ Please set your READWISE_TOKEN")
            print("   Either as an environment variable or edit line 17 in this script")
            return
        
        if NOTION_API_TOKEN == 'YOUR_NOTION_TOKEN_HERE':
            print("❌ Please set your NOTION_TOKEN")
            print("   Either as an environment variable or edit line 18 in this script")
            return
        
        if NOTION_DATABASE_ID == 'YOUR_DATABASE_ID_HERE':
            print("❌ Please set your NOTION_DATABASE_ID")
            print("   Either as an environment variable or edit line 19 in this script")
            return
        
        print("🚀 Readwise token: ✅")
        print("🚀 Notion token: ✅")
        print("🚀 Database ID: ✅\n")
        
        syncer = ReadwiseNotionSync()
        
        # Apply configuration overrides
        if args.all:
            print("⚠️  --all flag: Syncing ALL highlights (ignoring last sync time)\n")
            syncer.last_sync_time = None
        elif args.days:
            # Calculate the date N days ago
            days_ago = datetime.utcnow() - timedelta(days=args.days)
            syncer.last_sync_time = days_ago.isoformat() + 'Z'
            print(f"⚠️  --days {args.days}: Syncing highlights from last {args.days} days\n")
        elif DAYS_TO_SYNC and DAYS_TO_SYNC > 0:
            # Use configured DAYS_TO_SYNC if set
            days_ago = datetime.utcnow() - timedelta(days=DAYS_TO_SYNC)
            syncer.last_sync_time = days_ago.isoformat() + 'Z'
            print(f"⚙️  Configuration: Syncing highlights from last {DAYS_TO_SYNC} days\n")
        
        # Run FULL sync (only items with new highlights)
        syncer.full_sync()
        
        print("\n✅ Sync completed successfully!")
        
    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ ERROR OCCURRED:")
        print(f"   {type(e).__name__}: {str(e)}")
        print("\n📋 Full error details:")
        import traceback
        traceback.print_exc()
        print("=" * 60)
        traceback.print_exc()
        print("=" * 60)


if __name__ == "__main__":
    main()
