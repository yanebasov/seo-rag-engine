import os
import streamlit as st
import requests
from supabase import create_client
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# 1. Получение эмбеддинга запроса (768 dim)
def get_embedding(text: str):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={GEMINI_API_KEY}"
    payload = {
        "content": {"parts": [{"text": text}]},
        "outputDimensionality": 768
    }
    res = requests.post(url, json=payload)
    if res.status_code != 200:
        raise Exception(f"API Error ({res.status_code}): {res.text}")
    return res.json()["embedding"]["values"]

# 2. Вызов LLM
def generate_llm(prompt: str, temperature: float = 0.2):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature}
    }
    res = requests.post(url, json=payload)
    if res.status_code != 200:
        raise Exception(f"API Error ({res.status_code}): {res.text}")
    return res.json()["candidates"][0]["content"]["parts"][0]["text"]

# 3. Векторный поиск по Supabase
def retrieve_facts(query: str, top_k: int = 7, threshold: float = 0.35):
    vec = get_embedding(query)
    rpc_res = supabase.rpc("match_facts", {
        "query_embedding": vec,
        "match_threshold": threshold,
        "match_count": top_k,
        "filter_product": "pics.io"
    }).execute()
    return rpc_res.data

# --- ИНТЕРФЕЙС ---
st.set_page_config(page_title="SEO RAG Engine: Pics.io", layout="wide")
st.title("🎯 SEO RAG Generator & Fact-Checking Engine")

tab1, tab2 = st.tabs(["✍️ Генерация контента + Доктор", "📊 Аудит покрытия базы"])

with tab1:
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Входные SEO-данные")
        target_kw = st.text_input("Целевой ключевой запрос / Тема", value="AI Visual Search for marketing teams")
        content_type = st.selectbox("Тип контента", ["Feature Landing Page", "SEO Article Section", "Meta Title + Description + FAQ"])
        top_k = st.slider("Количество фактов из базы", 3, 15, 6)
        run_btn = st.button("🚀 Найти факты и сгенерировать", type="primary")

    if run_btn and target_kw:
        with st.spinner("Поиск фактов в Supabase..."):
            facts = retrieve_facts(target_kw, top_k=top_k)
            
        with col1:
            st.write(f"**Найдено фактов:** {len(facts)}")
            with st.expander("Посмотреть извлеченные факты", expanded=True):
                for f in facts:
                    st.markdown(f"- **[{f['category'].upper()}]** {f['claim']} *(Score: {f['similarity']:.2f})*")
                    if f.get("source_url"):
                        st.caption(f"Источник: {f['source_url']}")

        with col2:
            st.subheader("Сгенерированный контент")
            with st.spinner("Агент пишет текст..."):
                facts_context = "\n".join([f"- [{f['category']}] {f['claim']} (Источник: {f.get('source_url', '')})" for f in facts])
                
                gen_prompt = f"""
Ты — B2B SaaS SEO-копирайтер для Pics.io.
Напиши {content_type} под поисковый запрос "{target_kw}".

СТРОГИЕ ПРАВИЛА (Zero Hallucination):
1. Используй ТОЛЬКО факты из базы ниже.
2. Не придумывай функционал, которого нет в базе.
3. Учитывай ограничения (limitation), если они применимы.
4. Вставляй ссылки на источники в формате Markdown [Источник](url) при упоминании функций.

ФАКТЫ ИЗ БАЗЫ:
{facts_context}
"""
                generated_text = generate_llm(gen_prompt, temperature=0.2)
                st.markdown(generated_text)

            st.divider()
            st.subheader("🩺 Проверка агентом «Доктор»")
            with st.spinner("Агент Доктор сверяет факты..."):
                doc_prompt = f"""
Ты — фактчекер «Доктор».
Сверь сгенерированный текст с фактами:

ИСХОДНЫЕ ФАКТЫ:
{facts_context}

ТЕКСТ:
{generated_text}

Выдай вердикт:
1. Есть ли галлюцинации или неподтвержденные утверждения?
2. Не нарушены ли ограничения (limitation)?
3. Итоговый статус: ВЕРИФИЦИРОВАНО (PASS) или ТРЕБУЕТ ПРАВКИ (FAIL).
"""
                doc_verdict = generate_llm(doc_prompt, temperature=0.0)
                st.info(doc_verdict)

with tab2:
    st.subheader("Аудит покрытия базы знаний")
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