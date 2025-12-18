# services/openai_client.py
from openai import OpenAI
from config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

async def ask_gpt(prompt: str) -> str:
    """
    Отправляет текстовый запрос к GPT-4o-mini через новый responses API.
    Без reasoning, без o1, полностью безопасно.
    """
    try:
        response = client.responses.create(
            model="gpt-5-mini",
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt}  # ✅ обновлённый тип
                    ]
                }
            ],
            max_output_tokens=600,
        )

        # 🧾 Получаем текст ответа
        if response.output_text:
            return response.output_text.strip()

        # если модель вернула нестандартный формат
        for item in response.output or []:
            if item["type"] == "output_text":
                return item["content"][0]["text"].strip()

        return "⚠️ GPT не вернул текст."

    except Exception as e:
        return f"⚠️ Ошибка при обращении к GPT-5: {e}"
