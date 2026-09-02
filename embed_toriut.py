import os
import requests

# Подставь свои ключи
SUPABASE_URL = "https://brecncnpccxjcvjfgue.supabase.co"
SUPABASE_KEY = "ТВОЙ_SUPABASE_SERVICE_ROLE_ИЛИ_ANON_KEY"
GEMINI_KEY = "ТВОЙ_GEMINI_API_KEY"

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

def get_embedding(text):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={GEMINI_KEY}"
    res = requests.post(url, json={"content": {"parts": [{"text": text}]}}, timeout=10)
    if res.status_code == 200:
        return res.json()["embedding"]["values"][:768]
    print(f"Ошибка Gemini API: {res.text}")
    return None

# Выбираем только те строки, где вектор еще не создан
res = requests.get(f"{SUPABASE_URL}/rest/v1/toriut_facts?embedding=is.null&select=id,claim", headers=headers)
facts = res.json()

print(f"Фактов для векторизации: {len(facts)}")

for f in facts:
    vec = get_embedding(f["claim"])
    if vec:
        patch_res = requests.patch(
            f"{SUPABASE_URL}/rest/v1/toriut_facts?id=eq.{f['id']}",
            headers=headers,
            json={"embedding": vec}
        )
        if patch_res.status_code in (200, 204):
            print(f"Векторизован ID {f['id']}")
        else:
            print(f"Ошибка записи в Supabase для ID {f['id']}: {patch_res.text}")

print("Готово! Все эмбеддинги сохранены в базу.")
