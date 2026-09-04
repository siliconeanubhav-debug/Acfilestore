import re
from motor.motor_asyncio import AsyncIOMotorClient
from config import Config

client = AsyncIOMotorClient(Config.MONGO_URI)
db = client[Config.DB_NAME]
files_col = db["files"]

def parse_file_info(message):
    """कैप्शन से Title और Episode निकालता है, अगर कैप्शन नहीं है तो File Name यूज़ करता है।"""
    text_to_parse = ""
    
    if message.caption:
        text_to_parse = message.caption
    elif message.document and message.document.file_name:
        text_to_parse = message.document.file_name
    elif message.video and message.video.file_name:
        text_to_parse = message.video.file_name
    else:
        return None, None

    # Title: सिर्फ पहली लाइन (Anubhav Chaudhary's Ledger Rule)
    title_line = text_to_parse.split("\n")[0].strip()
    
    # Episode Regex: Ep 01, S01E05, [01], Episode 1
    ep_pattern = r'(?:E|EP|EPISODE|S\d+E|\[)\s*(\d{1,4})'
    match = re.search(ep_pattern, text_to_parse, re.IGNORECASE)
    
    ep_num = int(match.group(1)) if match else 1
    return title_line, ep_num

async def save_file_index(msg_id, title, raw_title, episode):
    await files_col.update_one(
        {"msg_id": msg_id},
        {"$set": {
            "title": title.lower(),
            "raw_title": raw_title,
            "episode": episode,
            "msg_id": msg_id
        }},
        upsert=True
    )

async def get_all_titles():
    return await files_col.distinct("title")

async def get_episodes_by_title(title):
    cursor = files_col.find({"title": title.lower()}).sort("episode", 1)
    return await cursor.to_list(length=None)

async def get_range_files(title, start_ep, end_ep):
    cursor = files_col.find({
        "title": title.lower(),
        "episode": {"$gte": start_ep, "$lte": end_ep}
    }).sort("episode", 1)
    return await cursor.to_list(length=None)
