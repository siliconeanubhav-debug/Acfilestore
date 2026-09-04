import re
import asyncio
import os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyromod import listen
from aiohttp import web
from fuzzywuzzy import process

from config import Config
from web import web_server
from database import (
    parse_file_info, 
    save_file_index, 
    get_all_titles, 
    get_episodes_by_title, 
    get_range_files
)

app = Client(
    "AC_FileStore_Bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)

# --- BATCH COMMAND (ADMIN SIDE) ---
@app.on_message(filters.command("batch") & filters.private & filters.user(Config.ADMIN_ID))
async def batch_handler(client: Client, message: Message):
    ask_first = await message.chat.ask("📌 DB Channel से **First Message Link** भेजें:")
    if not ask_first.text:
        return await message.reply("❌ अमान्य इनपुट!")

    ask_last = await message.chat.ask("📌 DB Channel से **Last Message Link** भेजें:")
    if not ask_last.text:
        return await message.reply("❌ अमान्य इनपुट!")
    
    try:
        first_id = int(ask_first.text.split("/")[-1])
        last_id = int(ask_last.text.split("/")[-1])
    except Exception:
        return await message.reply("❌ अमान्य Telegram Link Format!")

    indexed_count = 0
    status_msg = await message.reply("⏳ **AC File Store Bot** इंडेक्सिंग कर रहा है...")

    for msg_id in range(first_id, last_id + 1):
        try:
            db_msg = await client.get_messages(Config.DB_CHANNEL_ID, msg_id)
            if not db_msg or db_msg.empty:
                continue

            raw_title, ep_num = parse_file_info(db_msg)
            if raw_title:
                await save_file_index(msg_id, raw_title.lower(), raw_title, ep_num)
                indexed_count += 1
        except Exception as e:
            print(f"Indexing Error [{msg_id}]: {e}")

    await status_msg.edit_text(f"✅ **सफलता!** कुल **{indexed_count}** फाइलें इंडेक्स हो गईं।")

# --- GROUP SEARCH HANDLER (DIRECT QUERY WITH EPISODE PARSER) ---
@app.on_message(filters.group & filters.text)
async def group_search_handler(client: Client, message: Message):
    query = message.text.strip()
    if query.startswith("/"):
        return

    # 1. रिप्लाई वाला तरीका (Backwards Compatibility)
    if message.reply_to_message and message.reply_to_message.from_user.is_self:
        range_match = re.match(r'^(\d+)(?:-(\d+))?$', query)
        if range_match:
            start_ep = int(range_match.group(1))
            end_ep = int(range_match.group(2)) if range_match.group(2) else start_ep
            
            orig_text = message.reply_to_message.text
            series_name = ""
            if "`" in orig_text:
                series_name = orig_text.split("`")[1].strip()
            else:
                first_line = orig_text.split("\n")[0]
                series_name = first_line.replace("🎉", "").replace("उपलब्ध है!", "").strip()

            if series_name:
                files = await get_range_files(series_name, start_ep, end_ep)
                if not files:
                    return await message.reply("❌ मांगे गए एपिसोड डेटाबेस में उपलब्ध नहीं हैं।")

                msg_ids = "-".join([str(f["msg_id"]) for f in files])
                bot_username = (await client.get_me()).username
                pm_url = f"https://t.me/{bot_username}?start=get_{msg_ids}"

                btn = InlineKeyboardMarkup([[
                    InlineKeyboardButton("📥 Get Episodes in PM", url=pm_url)
                ]])
                return await message.reply(
                    f"✨ **{series_name}** (Episode {start_ep} - {end_ep}) तैयार हैं!\nनीचे बटन दबाकर PM में प्राप्त करें।",
                    reply_markup=btn
                )

    # 2. डायरेक्ट सर्च: क्वेरी से Episode नंबर / Range और Series Name को अलग करना
    # Example: "Destined Bride 3", "Destined Bride Ep 1-5", "Destined Bride Episode 4"
    ep_pattern = r'(?:ep|episode|episodes)?\s*(\d+)(?:\s*(?:to|-)\s*(\d+))?'
    match = re.search(ep_pattern, query, re.IGNORECASE)

    extracted_start_ep = None
    extracted_end_ep = None
    clean_query = query

    if match and match.group(1):
        extracted_start_ep = int(match.group(1))
        extracted_end_ep = int(match.group(2)) if match.group(2) else extracted_start_ep
        # सर्च मैचिंग के लिए मैसेज से एपिसोड वाला हिस्सा हटाना
        clean_query = re.sub(ep_pattern, '', query, flags=re.IGNORECASE).strip()

    all_titles = await get_all_titles()
    if not all_titles:
        return

    # टाइटल मैचिंग (साफ किए गए नाम के साथ)
    best_match, score = process.extractOne(clean_query.lower(), all_titles)
    if score >= 65:
        episodes = await get_episodes_by_title(best_match)
        if not episodes:
            return

        raw_title = episodes[0]["raw_title"]

        # 🟢 केस A: अगर यूजर ने मैसेज में ही Episode (1-5 या 3) लिख दिया था
        if extracted_start_ep is not None:
            files = await get_range_files(best_match, extracted_start_ep, extracted_end_ep)
            if files:
                msg_ids = "-".join([str(f["msg_id"]) for f in files])
                bot_username = (await client.get_me()).username
                pm_url = f"https://t.me/{bot_username}?start=get_{msg_ids}"

                btn = InlineKeyboardMarkup([[
                    InlineKeyboardButton("📥 Get Episodes in PM", url=pm_url)
                ]])
                return await message.reply(
                    f"✨ **{raw_title}** (Episode {extracted_start_ep} - {extracted_end_ep}) तैयार हैं!\nनीचे बटन दबाकर PM में प्राप्त करें।",
                    reply_markup=btn
                )
            else:
                return await message.reply(f"❌ **{raw_title}** के एपिसोड {extracted_start_ep}-{extracted_end_ep} डेटाबेस में नहीं मिले।")

        # 🟢 केस B: अगर सिर्फ कहानी का नाम लिखा है तो उपलब्ध एपिसोड की जानकारी देना
        min_ep = episodes[0]["episode"]
        max_ep = episodes[-1]["episode"]

        await message.reply(
            f"🎉 **`{raw_title}`** उपलब्ध है!\n\n"
            f"📌 **Available Episodes:** {min_ep} से {max_ep}\n"
            f"👇 **एपिसोड पाने के लिए:**\n"
            f"• सीधे टाइप करें: `{raw_title} 3` या `{raw_title} 1-5`\n"
            f"• या इस मैसेज पर `1-5` लिखकर रिप्लाई करें।"
        )

# --- PM START & FILE DELIVERY (WITH FORCE SUB) ---
@app.on_message(filters.private & filters.command("start"))
async def start_handler(client: Client, message: Message):
    # Force Sub Verification
    if Config.AUTH_CHANNEL:
        try:
            await client.get_chat_member(Config.AUTH_CHANNEL, message.from_user.id)
        except Exception:
            chat_info = await client.get_chat(Config.AUTH_CHANNEL)
            invite_link = chat_info.invite_link or f"https://t.me/{chat_info.username}"
            btn = InlineKeyboardMarkup([[
                InlineKeyboardButton("📢 Join Channel First", url=invite_link)
            ]])
            return await message.reply("⚠️ **फाइलों को प्राप्त करने के लिए कृपया हमारे अपडेट्स चैनल को जॉइन करें!**", reply_markup=btn)

    # Delivery Logic
    if len(message.command) > 1 and message.command[1].startswith("get_"):
        ids_str = message.command[1].replace("get_", "")
        msg_ids = [int(i) for i in ids_str.split("-")]

        await message.reply("🚚 **AC File Store Bot:** आपकी फाइलें भेजी जा रही हैं...")
        for m_id in msg_ids:
            try:
                await client.copy_message(
                    chat_id=message.from_user.id,
                    from_chat_id=Config.DB_CHANNEL_ID,
                    message_id=m_id
                )
            except Exception as e:
                print(f"Delivery Failed [{m_id}]: {e}")
    else:
        await message.reply(
            "<b>✨ <u>AC FILE STORE BOT</u> ✨</b>\n\n"
            "👤 <b>Developer:</b> अनुभव चौधरी\n"
            "🤖 **काम:** ग्रुप में ऑटो-सर्च और एपिसोड डिलीवरी।"
        )

# --- ASYNC MAIN RUNNER (RENDER COMPATIBLE) ---
async def start_services():
    await app.start()
    print("Bot Started Successfully!")

    web_app = await web_server()
    app_runner = web.AppRunner(web_app)
    await app_runner.setup()
    
    port = int(os.environ.get("PORT", Config.PORT))
    site = web.TCPSite(app_runner, "0.0.0.0", port)
    await site.start()
    print(f"Web Server running on port {port}")

    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(start_services())
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(app.stop())
