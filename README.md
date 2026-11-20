# MAX AUTO REACTION BOT (No OWNER_ID)

## Security
This version has no OWNER_ID setting. Administrative commands check Telegram admin status in the relevant registered group/channel. `/addchannel` requires the command sender to be an admin of that channel. Global `/status` and `/emojis` require admin status in at least one registered chat.

## Telegram limitation
Telegram Bot API lets one bot account set one reaction per message. This bot randomly chooses one emoji from your custom list for each new message; it cannot place 5–6 separate reactions on one post from the same bot.

## Setup
1. Revoke the 3 tokens shared in chat with @BotFather and create a fresh token.
2. Install Python 3.10+.
3. Run:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   ```
4. Put your NEW token in `.env`:
   ```env
   BOT_TOKEN=your_new_token
   DB_PATH=data/reactions.db
   ```
5. Start: `python bot.py`

## Add chats
- Group: add bot as admin with reaction permission, then send `/addchat` in the group as a group admin.
- Public channel: add bot as channel admin with reaction permission, then DM `/addchannel @channelusername`.
- Private channel: add bot as channel admin with reaction permission, then DM `/addchannel -1001234567890`. The sender must also be an admin of that private channel.

## Commands
`/start`, `/addchat`, `/addchannel @username`, `/addchannel -100...`, `/removechat`, `/removechannel -100...`, `/enable`, `/disable`, `/enablechat -100...`, `/disablechat -100...`, `/emojis 🔥 ❤️ 😍 👍`, `/status`.

## Railway
Push files to a private GitHub repository; do not upload `.env`. Create a worker, set `BOT_TOKEN` and `DB_PATH=/data/reactions.db`, mount a persistent volume at `/data`, then deploy. Procfile contains the worker command.
