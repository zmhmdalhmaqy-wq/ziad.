
---

## 6️⃣ ملف `telegram_bot.py`

```python
#!/usr/bin/env python3
import requests
import time
import threading

BOT_TOKEN = '8537430970:AAGHMgTYpG5U3vKHC3P8Kr28ZQyp4qOC1tU'
CHAT_ID = '6159656800'

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'HTML'}
    try:
        requests.post(url, json=data)
    except:
        pass

def send_document(file_name, content, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    files = {'document': (file_name, content)}
    data = {'chat_id': CHAT_ID, 'caption': caption, 'parse_mode': 'HTML'}
    try:
        requests.post(url, data=data, files=files)
    except:
        pass

def notify_server_start(server_id, owner_email, language, files):
    file_list = '\n'.join([f"• <code>{f.get('name')}</code>" for f in files])
    message = f"""
🚀 <b>سيرفر جديد - Ziad Host</b>

👤 <b>المستخدم:</b> {owner_email}
🖥️ <b>السيرفر:</b> <code>{server_id}</code>
💻 <b>اللغة:</b> {language}
📁 <b>عدد الملفات:</b> {len(files)}

<b>الملفات:</b>
{file_list}
    """
    send_message(message)

if __name__ == '__main__':
    print("🤖 Telegram Bot for Ziad Host is running...")
    while True:
        time.sleep(60)