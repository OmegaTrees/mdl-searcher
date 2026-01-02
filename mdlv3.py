"""
MyDramaList Search Bot - Clean Temporary Browser Version
Uses temporary browser instances without persistent profiles
"""

from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from typing import Dict
import os
import signal
import sys
import asyncio

# Import config
from config import API_ID, API_HASH, BOT_TOKEN

# ============================================================================
# MyDramaList Scraper
# ============================================================================

class MyDramaListScraper:
    """Async scraper for MyDramaList website using Playwright"""
    
    BASE_URL = "https://mydramalist.com"
    
    def __init__(self):
        self.playwright = None
        self.browser = None
    
    async def _ensure_browser(self):
        """Initialize browser if not already running"""
        if self.browser is None:
            self.playwright = await async_playwright().start()
            
            # Launch clean temporary Firefox browser
            print("🦊 Launching clean Firefox browser...")
            self.browser = await self.playwright.firefox.launch(
                headless=True,
                args=['--no-remote', '--private']
            )
            print("✅ Firefox launched successfully")
    
    async def _get_page_content(self, url):
        """Get page content using Playwright"""
        await self._ensure_browser()
        
        # Create a new context for each request (completely isolated)
        context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0'
        )
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_load_state("networkidle")
            content = await page.content()
            return content
        except Exception as e:
            print(f"Playwright error: {e}")
            return None
        finally:
            await page.close()
            await context.close()  # Close context to clean up
    
    async def search_dramas(self, query):
        """Search for dramas by title"""
        try:
            search_url = f"{self.BASE_URL}/search?q={query}"
            print(f"🔍 Searching: {search_url}")
            
            content = await self._get_page_content(search_url)
            if not content:
                return []
            
            soup = BeautifulSoup(content, 'html.parser')
            
            results = []
            drama_boxes = soup.find_all('div', class_='box', id=lambda x: x and x.startswith('mdl-'))
            
            for box in drama_boxes[:10]:  # Limit to 10 results
                title_tag = box.find('h6', class_='title')
                if not title_tag:
                    continue
                    
                link_tag = title_tag.find('a')
                if not link_tag:
                    continue
                
                title = link_tag.text.strip()
                url = link_tag.get('href', '')
                drama_id = box.get('id', '').replace('mdl-', '')
                
                # Get type and year
                type_info = box.find('span', class_='text-muted')
                type_year = type_info.text.strip() if type_info else ''
                
                results.append({
                    'id': drama_id,
                    'title': title,
                    'url': f"{self.BASE_URL}{url}",
                    'type_year': type_year
                })
            
            print(f"✅ Found {len(results)} results")
            return results
        except Exception as e:
            print(f"MDL Search error: {e}")
            return []
    
    async def get_drama_details(self, drama_url):
        """Get detailed information about a drama"""
        try:
            print(f"📄 Fetching details: {drama_url}")
            
            content = await self._get_page_content(drama_url)
            if not content:
                return None
            
            soup = BeautifulSoup(content, 'html.parser')
            
            # Title
            title_tag = soup.find('h1', class_='film-title')
            title = title_tag.text.strip() if title_tag else 'Unknown'
            
            # Image
            img_tag = soup.find('img', class_='img-responsive', alt=lambda x: x and 'poster' in x.lower())
            image_url = img_tag.get('src', '') if img_tag else ''
            if image_url and not image_url.startswith('http'):
                image_url = f"https:{image_url}" if image_url.startswith('//') else f"{self.BASE_URL}{image_url}"
            
            # Rating
            rating_div = soup.find('div', class_='col-film-rating')
            rating = rating_div.find('div', class_='box').text.strip() if rating_div else 'N/A'
            
            # Extract information
            info = {}
            info_list = soup.find_all('li', class_='list-item')
            
            for item in info_list:
                b_tag = item.find('b', class_='inline')
                if b_tag:
                    key = b_tag.text.strip().rstrip(':')
                    value = item.get_text(strip=True).replace(key + ':', '').strip()
                    info[key] = value
            
            # Synopsis
            synopsis_div = soup.find('div', class_='show-synopsis')
            synopsis = ''
            if synopsis_div:
                # Remove the edit link
                for link in synopsis_div.find_all('a'):
                    link.decompose()
                synopsis = synopsis_div.get_text(strip=True)
            
            # Genres
            genres_li = soup.find('li', class_='show-genres')
            genres = []
            if genres_li:
                genre_links = genres_li.find_all('a', class_='text-primary')
                genres = [link.text.strip() for link in genre_links]
            
            print(f"✅ Details fetched for: {title}")
            
            return {
                'title': title,
                'image_url': image_url,
                'rating': rating,
                'country': info.get('Country', info.get('Pays', 'N/A')),
                'type': info.get('Type', info.get('Catégorie', 'N/A')),
                'episodes': info.get('Episodes', info.get('Épisodes', 'N/A')),
                'aired': info.get('Aired', info.get('Diffusé', 'N/A')),
                'duration': info.get('Duration', info.get('Durée', 'N/A')),
                'genres': ', '.join(genres) if genres else 'N/A',
                'synopsis': synopsis[:500] + '...' if len(synopsis) > 500 else synopsis,
                'url': drama_url
            }
        except Exception as e:
            print(f"MDL Details error: {e}")
            return None
    
    async def close(self):
        """Close browser and cleanup"""
        try:
            print("🔥 Closing Firefox browser...")
            if self.browser:
                await self.browser.close()
                self.browser = None
                print("✅ Browser closed")
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
                print("✅ Playwright stopped")
        except Exception as e:
            print(f"Cleanup error: {e}")
            # Reset even on error to allow fresh start
            self.browser = None
            self.playwright = None


# ============================================================================
# Global instances
# ============================================================================
scraper = MyDramaListScraper()
user_data: Dict[int, Dict] = {}

# ============================================================================
# Create Pyrogram Client
# ============================================================================
app = Client(
    "mydramalist_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ============================================================================
# Bot Handlers
# ============================================================================

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Handle /start command"""
    await message.reply_text(
        "👋 <b>Welcome to MyDramaList Search Bot!</b>\n\n"
        "🔍 <b>Commands:</b>\n"
        "<code>/drama &lt;title&gt;</code> - Search for a drama\n"
        "<code>/help</code> - Show this message\n\n"
        "<b>Example:</b>\n"
        "<code>/drama Squid Game</code>",
        parse_mode=enums.ParseMode.HTML
    )

@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    """Handle /help command"""
    await message.reply_text(
        "📺 <b>MyDramaList Search Bot Help</b>\n\n"
        "<b>How to use:</b>\n"
        "1. Send <code>/drama &lt;title&gt;</code> to search for a drama\n"
        "2. Click on a result to view details\n\n"
        "<b>Examples:</b>\n"
        "<code>/drama Squid Game</code>\n"
        "<code>/drama Crash Landing on You</code>\n"
        "<code>/drama Kingdom</code>\n\n"
        "Bot will fetch information from MyDramaList.com",
        parse_mode=enums.ParseMode.HTML
    )

@app.on_message(filters.command("drama"))
async def drama_command(client: Client, message: Message):
    """Handle /drama command"""
    print(f"🎬 Drama command from user {message.from_user.id}")
    
    command_parts = message.text.split(maxsplit=1)
    
    if len(command_parts) < 2:
        await message.reply_text(
            "❌ Please provide a drama title to search.\n\n"
            "<b>Usage:</b> <code>/drama &lt;title&gt;</code>\n"
            "<b>Example:</b> <code>/drama Squid Game</code>",
            parse_mode=enums.ParseMode.HTML
        )
        return
    
    query = command_parts[1].strip()
    print(f"🔍 Searching for: {query}")
    
    # Send searching message
    searching_msg = await message.reply_text(
        f"🔍 Searching for: <b>{query}</b>...",
        parse_mode=enums.ParseMode.HTML
    )
    
    try:
        # Search dramas
        results = await scraper.search_dramas(query)
        
        # Close browser after search
        await scraper.close()
        print("🔥 Firefox closed after search")
        
        if not results:
            await searching_msg.edit_text(
                f"❌ No results found for: <b>{query}</b>\n\n"
                "Try a different search term.",
                parse_mode=enums.ParseMode.HTML
            )
            return
        
        # Store results in user data
        user_id = message.from_user.id
        user_data[user_id] = {
            'results': results,
            'query': query
        }
        
        # Create inline keyboard with results
        keyboard = []
        for drama in results:
            button_text = f"{drama['title']}"
            if drama['type_year']:
                button_text += f" ({drama['type_year']})"
            
            keyboard.append([
                InlineKeyboardButton(
                    button_text[:64],  # Telegram limit
                    callback_data=f"mdl_{drama['id']}"
                )
            ])
        
        await searching_msg.edit_text(
            f"📺 <b>Search Results for:</b> {query}\n\n"
            f"Found {len(results)} drama(s). Click to view details:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=enums.ParseMode.HTML
        )
        print(f"✅ Sent {len(results)} results to user")
    
    except Exception as e:
        print(f"❌ Drama command error: {e}")
        await scraper.close()  # Close on error too
        await searching_msg.edit_text(
            "❌ An error occurred while searching. Please try again.",
            parse_mode=enums.ParseMode.HTML
        )

@app.on_callback_query(filters.regex(r"^mdl_"))
async def drama_callback(client: Client, callback_query):
    """Handle button callbacks for drama selection"""
    print(f"📞 Callback: {callback_query.data}")
    
    await callback_query.answer()
    
    # Extract drama ID from callback data
    drama_id = callback_query.data.replace('mdl_', '')
    user_id = callback_query.from_user.id
    
    # Get drama URL from stored results
    if user_id not in user_data or 'results' not in user_data[user_id]:
        await callback_query.message.edit_text("❌ Error: Drama information not found. Please search again.")
        return
    
    drama_url = None
    for drama in user_data[user_id]['results']:
        if drama['id'] == drama_id:
            drama_url = drama['url']
            break
    
    if not drama_url:
        await callback_query.message.edit_text("❌ Error: Drama not found.")
        return
    
    # Send loading message
    await callback_query.message.edit_text("⏳ Loading drama details...")
    
    try:
        # Get drama details
        details = await scraper.get_drama_details(drama_url)
        
        if not details:
            await scraper.close()
            await callback_query.message.edit_text("❌ Error: Could not fetch drama details.")
            return
        
        # Format message
        caption = f"<b>{details['title']}</b>\n\n"
        caption += f"⭐ <b>Rating:</b> {details['rating']}/10\n"
        caption += f"🌍 <b>Country:</b> {details['country']}\n"
        caption += f"📺 <b>Type:</b> {details['type']}\n"
        caption += f"📊 <b>Episodes:</b> {details['episodes']}\n"
        caption += f"📅 <b>Aired:</b> {details['aired']}\n"
        caption += f"⏱ <b>Duration:</b> {details['duration']}\n"
        caption += f"🎭 <b>Genres:</b> {details['genres']}\n\n"
        caption += f"📖 <b>Synopsis:</b>\n{details['synopsis']}"
        
        # Create button for website link
        keyboard = [
            [InlineKeyboardButton("🌐 View on MyDramaList", url=details['url'])]
        ]
        
        # Send photo with details
        try:
            if details['image_url']:
                # Delete the searching message
                await callback_query.message.delete()
                
                # Send new message with photo
                await client.send_photo(
                    chat_id=callback_query.message.chat.id,
                    photo=details['image_url'],
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=enums.ParseMode.HTML
                )
                print("✅ Sent drama details with photo")
            else:
                # No image, send text only
                await callback_query.message.edit_text(
                    caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=enums.ParseMode.HTML,
                    disable_web_page_preview=True
                )
                print("✅ Sent drama details (text only)")
            
            # Wait a moment for upload to complete, then close Firefox
            await asyncio.sleep(1)
            await scraper.close()
            print("🔥 Firefox closed after posting to Telegram")
            
        except Exception as e:
            # If photo fails, send text only
            print(f"Photo send error: {e}")
            await callback_query.message.edit_text(
                caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True
            )
            await asyncio.sleep(1)
            await scraper.close()
            print("🔥 Firefox closed after posting to Telegram")
    
    except Exception as e:
        print(f"❌ Callback error: {e}")
        await scraper.close()  # Close on error too
        await callback_query.message.edit_text(
            "❌ An error occurred while fetching drama details. Please try again.",
            parse_mode=enums.ParseMode.HTML
        )

# ============================================================================
# Cleanup handlers
# ============================================================================

async def cleanup():
    """Cleanup function to close browser"""
    print("\n🧹 Starting cleanup...")
    await scraper.close()
    print("✅ Cleanup complete")

def signal_handler(signum, frame):
    """Handle interrupt signals"""
    print(f"\n⚠️ Received signal {signum}")
    import asyncio
    asyncio.create_task(cleanup())
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("🤖 MyDramaList Search Bot Starting...")
    print("=" * 50)
    print(f"📱 Bot Token: {BOT_TOKEN[:10]}...")
    print(f"🔑 API ID: {API_ID}")
    print("=" * 50)
    
    try:
        app.run()
    except KeyboardInterrupt:
        print("\n⏹ Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        print("🧹 Final cleanup...")
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(cleanup())
        loop.close()
        print("✅ Bot shutdown complete")
