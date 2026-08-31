import os
import streamlit as st
import requests
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# 1. Автоматический поиск рабочей модели эмбеддингов
@st.cache_resource
def get_model_info():
    for api_version in ["v1beta", "v1"]:
        url = f"https://generativelanguage.googleapis.com/{api_version}/models?key={GEMINI_API_KEY}"
        res = requests.get(url)
        if res.status_code == 200:
            models = res.json().get("models", [])
            for m in models:
                methods = m.get("supportedGenerationMethods", [])
                if "embedContent" in methods or "batchEmbedContents" in methods:
                    model_name = m["name"].replace("models/", "")
                    return api_version, model_name
    return "v1beta", "text-embedding-004"

API_VERSION, EMBED_MODEL = get_model_info()

# 2. Получение эмбеддинга (768 dim)
def get_embedding(text: str):
    url = f"https://generativelanguage.googleapis.com/{API_VERSION}/models/{EMBED_MODEL}:embedContent?key={GEMINI_API_KEY}"
    payload = {
        "content": {"parts": [{"text": text}]},
        "outputDimensionality": 768
    }
    res = requests.post(url, json=payload)
    if res.status_code != 200:
        # Fallback без outputDimensionality
        payload_fallback = {"content": {"parts": [{"text": text}]}}
        res_fb = requests.post(url, json=payload_fallback)
        if res_fb.status_code != 200:
            raise Exception(f"Ошибка API ({res.status_code}): {res.text}")
        vals = res_fb.json()["embedding"]["values"]
        return vals[:768]
    return res.json()["embedding"]["values"]

# 3. Вызов LLM генератора
def generate_llm(prompt: str, temperature: float = 0.2):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature}
    }
    res = requests.post(url, json=payload)
    if res.status_code != 200:
        raise Exception(f"Ошибка генерации LLM ({res.status_code}): {res.text}")
    return res.json()["candidates"][0]["content"]["parts"][0]["text"]

# 4. Поиск релевантных фактов в Supabase
def retrieve_facts(query: str, top_k: int = 6, threshold: float = 0.30):
    vec = get_embedding(query)
    rpc_res = supabase.rpc("match_facts", {
        "query_embedding": vec,
        "match_threshold": threshold,
        "match_count": top_k,
        "filter_product": "pics.io"
    }).execute()
    return rpc_res.data

# --- UI ИНТЕРФЕЙС ---
st.set_page_config(page_title="SEO RAG Engine: Pics.io", layout="wide")
st.title("🎯 SEO RAG Generator & Fact-Checking Engine")

tab1, tab2 = st.tabs(["✍️ Генерация контента + Доктор", "📊 Аудит покрытия базы (Gap Audit)"])

with tab1:
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Входные SEO-данные")
        target_kw = st.text_input("Целевой ключевой запрос / Тема", value="Google Drive DAM integration features and limitations")
        content_type = st.selectbox("Тип контента", ["Feature Landing Page", "SEO Article Section", "Meta Title + Description + FAQ"])
        top_k = st.slider("Количество фактов из базы", 3, 15, 6)
        run_btn = st.button("🚀 Найти факты и сгенерировать", type="primary")

    if run_btn and target_kw:
        with st.spinner("Извлечение верифицированных фактов из Supabase..."):
            facts = retrieve_facts(target_kw, top_k=top_k)
            
        with col1:
            st.write(f"**Найдено фактов:** {len(facts)}")
            with st.expander("Посмотреть извлеченные факты", expanded=True):
                if not facts:
                    st.warning("Фактов выше порога сходства не найдено. Попробуйте уменьшить порог или изменить запрос.")
                for f in facts:
                    st.markdown(f"- **[{f['category'].upper()}]** {f['claim']} *(Score: {f['similarity']:.2f})*")
                    if f.get("source_url"):
                        st.caption(f"Источник: {f['source_url']}")

        if facts:
            with col2:
                st.subheader("Сгенерированный контент")
                with st.spinner("Генерация текста..."):
                    facts_context = "\n".join([f"- [{f['category']}] {f['claim']} (Источник: {f.get('source_url', '')})" for f in facts])
                    
                    gen_prompt = f"""
Ты — профессиональный B2B SaaS SEO-копирайтер для Pics.io.
Напиши {content_type} под поисковый запрос "{target_kw}".

СТРОГИЕ ПРАВИЛА (Zero Hallucination):
1. Используй ТОЛЬКО факты из базы ниже.
2. Категорически запрещено придумывать функции, которых нет в фактах.
3. Обязательно честно упоминай ограничения (limitation), если они есть в фактах.
4. Вставляй ссылки на источники в формате Markdown [Источник](url) при описании возможностей.

ФАКТЫ ИЗ БАЗЫ:
{facts_context}
"""
                    generated_text = generate_llm(gen_prompt, temperature=0.2)
                    st.markdown(generated_text)

                st.divider()
                st.subheader("🩺 Проверка агентом «Доктор»")
                with st.spinner("Агент Доктор сверяет факты..."):
                    doc_prompt = f"""
Ты — строгий фактчекер «Доктор».
Сверь сгенерированный текст с исходными фактами:

ИСХОДНЫЕ ФАКТЫ:
{facts_context}

СГЕНЕРИРОВАННЫЙ ТЕКСТ:
{generated_text}

Выдай вердикт:
1. Есть ли галлюцинации или неподтвержденные утверждения?
2. Не нарушены ли ограничения (limitation)?
3. Итоговый статус: ВЕРИФИЦИРОВАНО (PASS) или ТРЕБУЕТ ПРАВКИ (FAIL).
"""
                    doc_verdict = generate_llm(doc_prompt, temperature=0.0)
                    st.info(doc_verdict)

with tab2:
    st.subheader("Аудит покрытия базы знаний (Gap Audit)")
    st.caption("Проверьте, достаточно ли фактов в базе для ранжирования по запросу.")
    test_query = st.text_input("Поисковый запрос для аудита", value="Can Pics.io automatically tag faces in video?")
    if st.button("Проверить сходство"):
        test_facts = retrieve_facts(test_query, top_k=3, threshold=0.1)
        if test_facts:
            best_score = test_facts[0]["similarity"]
            if best_score > 0.65:
                st.success(f"Отличное покрытие! Score: {best_score:.2f}")
            elif best_score > 0.45:
                st.warning(f"Среднее покрытие ({best_score:.2f}). Рекомендуется добавить точный факт в Excel/Supabase.")
            else:
                st.error(f"Слепая зона ({best_score:.2f})! В базе нет фактов по этому вопросу.")
            for tf in test_facts:
                st.write(f"- {tf['claim']} *(Score: {tf['similarity']:.2f})*")
