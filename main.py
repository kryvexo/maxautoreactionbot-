import asyncio
import logging
import os
import random

import aiosqlite
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, Chat, ReactionTypeEmoji, BotCommand

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "").strip()
DB_PATH = os.getenv("DB_PATH", "data/reactions.db")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN missing. Add a fresh token to .env / hosting variables.")

DEFAULT_EMOJIS = ["🔥", "❤️", "😍", "👍", "⚡", "🥰"]
router = Router()
dp = Dispatcher()
dp.include_router(router)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("max-auto-reaction")


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY, title TEXT NOT NULL,
            chat_type TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT NOT NULL
        )""")
        await db.commit()


async def save_chat(chat: Chat):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""INSERT INTO chats(chat_id,title,chat_type,enabled)
            VALUES(?,?,?,1) ON CONFLICT(chat_id) DO UPDATE SET
            title=excluded.title, chat_type=excluded.chat_type""",
            (chat.id, chat.title or chat.username or str(chat.id), chat.type))
        await db.commit()


async def is_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


async def admin_of_any_registered_chat(message: Message, bot: Bot) -> bool:
    if not message.from_user:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT chat_id FROM chats")
        ids = [row[0] for row in await cur.fetchall()]
        await cur.close()
    for chat_id in ids:
        if await is_admin(bot, chat_id, message.from_user.id):
            return True
    return False


async def set_enabled(chat_id: int, enabled: bool) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("UPDATE chats SET enabled=? WHERE chat_id=?",
                               (int(enabled), chat_id))
        changed = cur.rowcount
        await db.commit()
    return changed > 0


async def remove_chat(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM chats WHERE chat_id=?", (chat_id,))
        await db.commit()


async def is_enabled(chat_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT enabled FROM chats WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        await cur.close()
    return bool(row and row[0])


async def get_emojis():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key='emojis'")
        row = await cur.fetchone()
        await cur.close()
    return row[0].split() if row else DEFAULT_EMOJIS


async def save_emojis(emojis):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""INSERT INTO settings(key,value) VALUES('emojis',?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            (" ".join(emojis),))
        await db.commit()


HELP = """🔥 MAX AUTO REACTION BOT

Setup:
• Add bot as admin in your group/channel.
• Allow it to add reactions.

Commands:
 /addchat — register this group (group admin)
 /addchannel @username — register public channel
 /addchannel -1001234567890 — register private channel
 /removechat — remove current chat (chat admin)
 /removechannel CHAT_ID — remove a channel (channel admin)
 /enable /disable — toggle current chat
 /enablechat CHAT_ID /disablechat CHAT_ID — toggle by ID
 /emojis 🔥 ❤️ 😍 👍 — set custom emoji list
 /status — show registered chats

Note: Bot API supports one reaction per message from this bot account."""


@router.message(Command("start", "help"))
async def start(message: Message):
    await message.answer(HELP)


@router.message(Command("addchat"))
async def add_group(message: Message, bot: Bot):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("Use /addchat inside the target group.")
        return
    if not message.from_user or not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.answer("Only a group administrator can register this group.")
        return
    me = await bot.get_me()
    if not await is_admin(bot, message.chat.id, me.id):
        await message.answer("Make the bot an administrator and allow it to add reactions.")
        return
    await save_chat(message.chat)
    await message.answer(f"✅ Registered: {message.chat.title}")


@router.message(Command("addchannel"))
async def add_channel(message: Message, bot: Bot):
    if message.chat.type != "private" or not message.from_user:
        await message.answer("Send this command to the bot in private chat.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Usage:\n/addchannel @publicchannel\n/addchannel -1001234567890")
        return
    raw = parts[1].strip()
    try:
        channel = await bot.get_chat(int(raw) if raw.lstrip("-").isdigit() else raw)
        if channel.type != "channel":
            raise ValueError("That ID/username is not a channel.")
        if not await is_admin(bot, channel.id, message.from_user.id):
            raise PermissionError("You must be an administrator of that channel.")
        me = await bot.get_me()
        if not await is_admin(bot, channel.id, me.id):
            raise PermissionError("Add this bot as channel administrator first, with reaction permission.")
        await save_chat(channel)
        await message.answer(f"✅ Registered channel: {channel.title or channel.id}\nID: {channel.id}")
    except Exception as exc:
        await message.answer(f"❌ Could not register channel: {exc}")


async def target_admin_action(message: Message, bot: Bot, action: str):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("Provide numeric chat ID, e.g. -1001234567890")
        return
    target_id = int(parts[1])
    if not message.from_user or not await is_admin(bot, target_id, message.from_user.id):
        await message.answer("You must be an administrator of that target chat/channel.")
        return
    if action == "remove":
        await remove_chat(target_id)
        await message.answer("🗑️ Chat removed if it was registered.")
    else:
        changed = await set_enabled(target_id, action == "enable")
        await message.answer(("✅ Enabled." if action == "enable" else "⏸️ Disabled.")
                             if changed else "Chat is not registered.")


@router.message(Command("removechat"))
async def remove_current(message: Message, bot: Bot):
    if not message.from_user or not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.answer("Only an administrator of this chat can do that.")
        return
    await remove_chat(message.chat.id)
    await message.answer("🗑️ Chat removed if registered.")


@router.message(Command("removechannel"))
async def remove_channel(message: Message, bot: Bot):
    await target_admin_action(message, bot, "remove")


@router.message(Command("enablechat"))
async def enable_chat(message: Message, bot: Bot):
    await target_admin_action(message, bot, "enable")


@router.message(Command("disablechat"))
async def disable_chat(message: Message, bot: Bot):
    await target_admin_action(message, bot, "disable")


@router.message(Command("enable"))
async def enable_current(message: Message, bot: Bot):
    if not message.from_user or not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.answer("Only an administrator of this chat can do that.")
        return
    changed = await set_enabled(message.chat.id, True)
    await message.answer("✅ Enabled." if changed else "This chat is not registered.")


@router.message(Command("disable"))
async def disable_current(message: Message, bot: Bot):
    if not message.from_user or not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.answer("Only an administrator of this chat can do that.")
        return
    changed = await set_enabled(message.chat.id, False)
    await message.answer("⏸️ Disabled." if changed else "This chat is not registered.")


@router.message(Command("emojis"))
async def emoji_settings(message: Message, bot: Bot):
    if not await admin_of_any_registered_chat(message, bot):
        await message.answer("Only an admin of a registered chat can change global reactions.")
        return
    emojis = (message.text or "").split()[1:]
    if not emojis:
        await message.answer("Example: /emojis 🔥 ❤️ 😍 👍 ⚡ 🥰")
        return
    if len(emojis) > 20 or len(set(emojis)) != len(emojis):
        await message.answer("Use 1–20 unique emoji.")
        return
    await save_emojis(emojis)
    await message.answer("✅ Saved: " + " ".join(emojis))


@router.message(Command("status"))
async def status(message: Message, bot: Bot):
    if not await admin_of_any_registered_chat(message, bot):
        await message.answer("Only an admin of a registered chat can view status.")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT chat_id,title,chat_type,enabled FROM chats ORDER BY title")
        rows = await cur.fetchall()
        await cur.close()
    listing = "\n".join(
        f"{'🟢' if enabled else '⚪'} {title} | {kind} | {chat_id}"
        for chat_id, title, kind, enabled in rows
    ) or "No chats registered."
    await message.answer(f"📊 Registered chats: {len(rows)}\nReactions: {' '.join(await get_emojis())}\n\n{listing}")


async def react(bot: Bot, message: Message):
    if not await is_enabled(message.chat.id):
        return
    emoji = random.choice(await get_emojis())
    try:
        await bot.set_message_reaction(
            chat_id=message.chat.id,
            message_id=message.message_id,
            reaction=[ReactionTypeEmoji(emoji=emoji)]
        )
        log.info("Reacted %s in chat %s", emoji, message.chat.id)
    except Exception as exc:
        log.warning("Reaction failed in chat %s: %s", message.chat.id, exc)


@router.message(F.chat.type.in_({"group", "supergroup"}))
async def group_message(message: Message, bot: Bot):
    if message.from_user and message.from_user.is_bot:
        return
    await react(bot, message)


@router.channel_post()
async def channel_post(message: Message, bot: Bot):
    await react(bot, message)


async def main():
    await init_db()
    bot = Bot(TOKEN)
    await bot.set_my_commands([
        BotCommand(command="start", description="Help"),
        BotCommand(command="status", description="Registered chats"),
        BotCommand(command="emojis", description="Set custom reactions"),
    ])
    log.info("MAX AUTO REACTION BOT starting")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
