# AI Assistant Telegram Bot

Telegram AI assistant built with **Python** and **aiogram 3**, focused on automation, structured responses, and asynchronous workflows.

## Features
- Telegram Bot API (aiogram 3)
- Asynchronous handlers (`async` / `await`)
- Background tasks and scheduler
- LLM integration (OpenAI-compatible API)
- Structured and predictable responses
- User settings and statistics
- Clean project structure

## Tech Stack
- Python 3.10+
- aiogram 3
- asyncio
- APScheduler
- OpenAI API (or compatible LLM provider)

## Project Structure
.
├── bot/ # Telegram bot handlers and routers
├── services/ # AI client, scheduler, business logic
├── middlewares/ # Bot middlewares
├── keyboards/ # Inline / reply keyboards
├── config/ # App configuration
├── main.py # Entry point

bash
Копировать код

## Setup & Run
```bash
git clone https://github.com/naimaaan/ai-assistant-bot.git
cd ai-assistant-bot

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env
python main.py
Notes
.env contains secrets and is not committed

This project demonstrates Telegram automation and AI workflows
