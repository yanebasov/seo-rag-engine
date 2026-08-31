import pandas as pd
import requests
from supabase import create_client

# Настройки доступа
SUPABASE_URL = "https://brecncznpccxjcvjfgue.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJyZWNuY3pucGNjeGpjdmpmZ3VlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODgxNzA5MTgsImV4cCI6MjEwMzc0NjkxOH0.cd9nwvzgeWYemPSOfA2luW1d_AJoKEr-pn-ob0X_X80"

# Вставьте ваш ключ Gemini
GEMINI_API_KEY = "AIzaSyCTVQfJSWvapiWCF8yWhydETQV1ObjZilY"

EXCEL_PATH = "pics_io_facts_v4.xlsx"

# Инициализация Supabase
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 1. Поиск модели
def find_embedding_model(api_key: str):
    for api_version in ["v1beta", "v1"]:
        url = f"https://generativelanguage.googleapis.com/{api_version}/models?key={api_key}"
        res = requests.get(url)
        if res.status_code == 200:
            models = res.json().get("models", [])
            for m in models:
                methods = m.get("supportedGenerationMethods", [])
                if "embedContent" in methods or "batchEmbedContents" in methods:
                    model_name = m["name"].replace("models/", "")
                    return api_version, model_name
    return "v1beta", "text-embedding-004"

api_version, model_name = find_embedding_model(GEMINI_API_KEY)
print(f"Используем модель: {model_name} ({api_version}) с размерностью 768")

# 2. Функция генерации эмбеддинга строго на 768 измерений
def get_embedding(text: str, api_key: str, version: str, model: str):
    url = f"https://generativelanguage.googleapis.com/{version}/models/{model}:embedContent?key={api_key}"
    payload = {
        "content": {
            "parts": [{"text": text}]
        },
        "outputDimensionality": 768
    }
    response = requests.post(url, json=payload)
    if response.status_code != 200:
        # Fallback без outputDimensionality, если модель старая
        payload_fallback = {"content": {"parts": [{"text": text}]}}
        res_fallback = requests.post(url, json=payload_fallback)
        if res_fallback.status_code != 200:
            raise Exception(f"Ошибка Gemini API ({response.status_code}): {response.text}")
        vals = res_fallback.json()["embedding"]["values"]
        return vals[:768]
        
    return response.json()["embedding"]["values"]

# 3. Чтение и импорт
df = pd.read_excel(EXCEL_PATH, sheet_name="facts")
records = []

print(f"Генерация эмбеддингов для {len(df)} фактов...")

for idx, row in df.iterrows():
    claim_text = str(row["claim"])
    print(f"[{idx + 1}/{len(df)}] {claim_text[:45]}...")
    
    embedding = get_embedding(claim_text, GEMINI_API_KEY, api_version, model_name)

    records.append({
        "id": int(row["id"]),
        "product": str(row["product"]),
        "category": str(row["category"]),
        "claim": claim_text,
        "source_url": str(row["source_url"]) if pd.notna(row["source_url"]) else None,
        "source_type": str(row["source_type"]) if pd.notna(row["source_type"]) else None,
        "authority_score": int(row["authority_score"]) if pd.notna(row["authority_score"]) else None,
        "human_approved": bool(row["human_approved"]),
        "date_added": str(row["date_added"]) if pd.notna(row["date_added"]) else None,
        "notes": str(row["notes"]) if pd.notna(row["notes"]) else None,
        "embedding": embedding
    })

# 4. Запись в Supabase
supabase.table("pics_facts").upsert(records).execute()
print(f"\nГотово! Все {len(records)} записей успешно записаны в Supabase.")