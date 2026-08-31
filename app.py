import os
import json
import streamlit as st
import pandas as pd
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

def get_secret(key, default=""):
    val = ""
    if hasattr(st, "secrets") and key in st.secrets:
        val = str(st.secrets[key])
    else:
        val = str(os.getenv(key, default))
    return val.strip().strip("'").strip('"')

SUPABASE_URL = get_secret("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = get_secret("SUPABASE_KEY", "")
DEFAULT_GEMINI_KEY = get_secret("GEMINI_API_KEY", "")

# Авторизация
AUTH_USERS = {"slava": "slava2026", "teamlead": "picslead2026"}
if hasattr(st, "secrets") and "AUTH_USERS" in st.secrets:
    try:
        sec_auth = st.secrets["AUTH_USERS"]
        if hasattr(sec_auth, "items"):
            AUTH_USERS.update({str(k).lower().strip(): str(v).strip() for k, v in sec_auth.items()})
        elif isinstance(sec_auth, str) and sec_auth.strip():
            parsed = json.loads(sec_auth.replace("'", '"'))
            AUTH_USERS.update({str(k).lower().strip(): str(v).strip() for k, v in parsed.items()})
    except Exception:
        pass

st.set_page_config(page_title="SEO RAG Enterprise Hub", layout="wide", page_icon="🎯")

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
    st.session_state["username"] = None

if not st.session_state["authenticated"]:
    st.markdown("### 🔐 Авторизация в SEO RAG Hub")
    col1, _ = st.columns([1, 2])
    with col1:
        user_input = st.text_input("Логин")
        pass_input = st.text_input("Пароль", type="password")
        if st.button("Войти", type="primary"):
            u = user_input.strip().lower()
            p = pass_input.strip()
            if u in AUTH_USERS and AUTH_USERS[u] == p:
                st.session_state["authenticated"] = True
                st.session_state["username"] = u
                st.rerun()
            else:
                st.error("Неверный логин или пароль")
    st.stop()

# Инициализация и сохранение API ключа в сессии
if "gemini_api_key" not in st.session_state:
    st.session_state["gemini_api_key"] = DEFAULT_GEMINI_KEY

# --- САЙДБАР ---
with st.sidebar:
    st.success(f"👤 Пользователь: **{st.session_state['username']}**")
    if st.button("🚪 Выйти"):
        st.session_state["authenticated"] = False
        st.session_state["username"] = None
        st.rerun()
    st.divider()
    selected_product = st.selectbox(
        "🏢 Выбор продукта:",
        options=["pics.io", "toriut"],
        format_func=lambda x: "Pics.io (DAM)" if x == "pics.io" else "Toriut (PIM)"
    )
    st.divider()
    key_input = st.text_input("🔑 Gemini API Key:", value=st.session_state["gemini_api_key"], type="password")
    if key_input:
        st.session_state["gemini_api_key"] = key_input.strip().strip("'").strip('"')

CURRENT_GEMINI_KEY = st.session_state["gemini_api_key"]

def get_supabase_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

def get_embedding(text: str):
    if not CURRENT_GEMINI_KEY:
        st.error("Пожалуйста, вставьте рабочий Gemini API Key в левом меню.")
        return None

    models = ["text-embedding-004", "embedding-001"]
    last_err = ""
    for m in models:
        for ver in ["v1beta", "v1"]:
            url = f"https://generativelanguage.googleapis.com/{ver}/models/{m}:embedContent?key={CURRENT_GEMINI_KEY}"
            payload = {"content": {"parts": [{"text": text}]}}
            try:
                res = requests.post(url, json=payload, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    if "embedding" in data and "values" in data["embedding"]:
                        return data["embedding"]["values"][:768]
                elif res.status_code != 404:
                    st.error(f"⚠️ Ошибка Google API ({res.status_code}): {res.text}")
                    return None
                last_err = f"{res.status_code}: {res.text}"
            except Exception as e:
                last_err = str(e)
                continue

    st.error(f"Не удалось получить эмбеддинг: {last_err}")
    return None

def generate_llm(prompt: str, temperature: float = 0.2):
    if not CURRENT_GEMINI_KEY:
        return "Ошибка: отсутствует Gemini API Key."

    models = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
    last_err = ""
    for m in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={CURRENT_GEMINI_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature}
        }
        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                data = res.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
            elif res.status_code != 404:
                st.error(f"⚠️ Ошибка генерации ({res.status_code}): {res.text}")
                return "Ошибка генерации ответа от Google API."
            last_err = f"{res.status_code}: {res.text}"
        except Exception as e:
            last_err = str(e)
            continue

    st.error(f"⚠️ Ошибка вызова моделей LLM: {last_err}")
    return "Не удалось сгенерировать текст."

def retrieve_facts(query: str, product: str, top_k: int = 6, threshold: float = 0.0):
    vec = get_embedding(query)
    if not vec:
        return []
    url = f"{SUPABASE_URL}/rest/v1/rpc/match_facts"
    payload = {
        "query_embedding": vec,
        "match_threshold": threshold,
        "match_count": top_k,
        "filter_product": product
    }
    try:
        res = requests.post(url, headers=get_supabase_headers(), json=payload, timeout=10)
        if res.status_code == 200:
            return res.json()
        st.error(f"Supabase RPC Error: {res.status_code} - {res.text}")
    except Exception as e:
        st.error(f"Ошибка базы данных: {e}")
    return []

def retrieve_linking_pages(query: str, product: str, top_k: int = 4, threshold: float = 0.0):
    vec = get_embedding(query)
    if not vec:
        return []
    url = f"{SUPABASE_URL}/rest/v1/rpc/match_site_pages"
    payload = {
        "query_embedding": vec,
        "match_threshold": threshold,
        "match_count": top_k,
        "filter_product": product
    }
    try:
        res = requests.post(url, headers=get_supabase_headers(), json=payload, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []

def save_generation_to_history(product, author, kw, content_type, text, verdict):
    url = f"{SUPABASE_URL}/rest/v1/content_history"
    headers = get_supabase_headers()
    headers["Prefer"] = "return=minimal"
    payload = {
        "product": product,
        "author": author,
        "target_keyword": kw,
        "content_type": content_type,
        "generated_text": text,
        "doctor_verdict": verdict,
        "status": "PASS" if "PASS" in str(verdict).upper() else "FAIL"
    }
    try:
        requests.post(url, headers=headers, json=payload, timeout=8)
    except Exception:
        pass

def get_content_history(product: str):
    url = f"{SUPABASE_URL}/rest/v1/content_history?product=eq.{product}&order=created_at.desc&limit=20"
    try:
        res = requests.get(url, headers=get_supabase_headers(), timeout=8)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []

st.title(f"🎯 SEO RAG Hub — {selected_product.upper()}")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "✍️ Генерация + Перелинковка + Доктор",
    "⚡ Пакетная генерация (Batch)",
    "🔗 Векторный линк-билдер",
    "📊 Gap Audit (Покрытие)",
    "📜 История генераций"
])

# 1. ГЕНЕРАЦИЯ
with tab1:
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("SEO параметры")
        target_kw = st.text_input("Целевой ключевой запрос", value="Google Drive DAM integration features and limitations")
        content_type = st.selectbox("Тип контента", ["Feature Landing Page", "SEO Article Section", "Meta Title + Description + FAQ"])
        top_k = st.slider("Количество фактов", 2, 12, 6)
        top_links_count = st.slider("Количество внутренних ссылок", 1, 6, 3)
        run_btn = st.button("🚀 Сгенерировать контент", type="primary")

    if run_btn and target_kw:
        with st.spinner("Поиск фактов и страниц для перелинковки..."):
            facts = retrieve_facts(target_kw, selected_product, top_k=top_k)
            pages = retrieve_linking_pages(target_kw, selected_product, top_k=top_links_count)
            
        with col1:
            st.write(f"**Найдено фактов:** {len(facts)}")
            with st.expander("Извлеченные факты", expanded=True):
                if not facts:
                    st.warning("Факты не найдены.")
                for f in facts:
                    st.markdown(f"- **[{f.get('category','').upper()}]** {f.get('claim','')} *(Score: {f.get('similarity', 0):.2f})*")
            
            st.write(f"**Страницы для перелинковки:** {len(pages)}")
            with st.expander("Подобранные внутренние URL", expanded=True):
                if not pages:
                    st.info("Страницы перелинковки еще не загружены.")
                for p in pages:
                    st.markdown(f"- [{p.get('title','')}]({p.get('url','')}) *(Score: {p.get('similarity', 0):.2f})*")

        if facts:
            with col2:
                st.subheader("Результат генерации")
                with st.spinner("Генерация текста с внедрением ссылок..."):
                    facts_context = "\n".join([f"- [{f.get('category','')}] {f.get('claim','')} (Source: {f.get('source_url', '')})" for f in facts])
                    links_context = "\n".join([f"- [{p.get('title','')}]({p.get('url','')})" for p in pages]) if pages else "Внутренние ссылки отсутствуют"
                    
                    gen_prompt = f"""
Ты — профессиональный B2B SaaS SEO-копирайтер для {selected_product}.
Напиши {content_type} под поисковый запрос "{target_kw}".

СТРОГИЕ ПРАВИЛА:
1. Используй ТОЛЬКО факты из базы ниже.
2. Не придумывай функций, которых нет в фактах.
3. Органично вставь в текст 2-3 релевантных внутренних ссылки из блока СТРАНИЦЫ ДЛЯ ПЕРЕЛИНКОВКИ в виде Markdown [Анкор](url).
4. Обязательно указывай ограничения (limitation), если они применимы.

ФАКТЫ:
{facts_context}

СТРАНИЦЫ ДЛЯ ПЕРЕЛИНКОВКИ:
{links_context}
"""
                    generated_text = generate_llm(gen_prompt, temperature=0.2)
                    st.markdown(generated_text)

                st.divider()
                st.subheader("🩺 Аудит агентом «Доктор»")
                with st.spinner("Проверка на галлюцинации..."):
                    doc_prompt = f"""
Проверь текст на соответствие фактам:
ФАКТЫ:
{facts_context}

ТЕКСТ:
{generated_text}

Вердикт:
1. Есть галлюцинации?
2. Корректно ли интегрированы ссылки?
3. Статус: ВЕРИФИЦИРОВАНО (PASS) или ТРЕБУЕТ ПРАВКИ (FAIL).
"""
                    doc_verdict = generate_llm(doc_prompt, temperature=0.0)
                    st.info(doc_verdict)
                    save_generation_to_history(selected_product, st.session_state["username"], target_kw, content_type, generated_text, doc_verdict)
                    st.success("💾 Результат сохранен в историю!")

# 2. ПАКЕТНАЯ ГЕНЕРАЦИЯ
with tab2:
    st.subheader("⚡ Пакетная генерация")
    batch_input = st.text_area("Список ключевых слов (по одному на строку)", height=140, value="Google Drive DAM integration\nShopify PIM catalog sync\nAI Visual search workflow")
    batch_type = st.selectbox("Формат вывода", ["Meta Title + Description + FAQ", "SEO Article Section", "Feature Landing Page"])
    
    if st.button("🚀 Запустить пакетную обработку"):
        keywords = [k.strip() for k in batch_input.split("\n") if k.strip()]
        results = []
        bar = st.progress(0)
        for i, kw in enumerate(keywords):
            facts = retrieve_facts(kw, selected_product, top_k=4)
            pages = retrieve_linking_pages(kw, selected_product, top_k=2)
            facts_txt = "\n".join([f"- {f.get('claim','')}" for f in facts])
            links_txt = "\n".join([f"- [{p.get('title','')}]({p.get('url','')})" for p in pages])
            prompt = f"Напиши {batch_type} для {selected_product} по теме '{kw}'. Использовать только эти факты:\n{facts_txt}\nВнутренние ссылки:\n{links_txt}"
            txt = generate_llm(prompt)
            results.append({"Keyword": kw, "Generated_Content": txt, "Links": ", ".join([p.get('url','') for p in pages])})
            bar.progress((i + 1) / len(keywords))
        
        df_res = pd.DataFrame(results)
        st.dataframe(df_res)
        csv_data = df_res.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Скачать CSV", data=csv_data, file_name=f"batch_{selected_product}.csv", mime="text/csv")

# 3. ВЕКТОРНЫЙ ЛИНК-БИЛДЕР
with tab3:
    st.subheader("🔗 Векторный подбор страниц сайта (Internal Link Finder)")
    search_link_kw = st.text_input("Фрагмент текста или тема для подбора URL", value="Digital Asset Management for eCommerce")
    if st.button("Найти URL для перелинковки"):
        found_pages = retrieve_linking_pages(search_link_kw, selected_product, top_k=8, threshold=0.0)
        if not found_pages:
            st.info("Страницы перелинковки еще не загружены в таблицу site_pages.")
        for fp in found_pages:
            st.markdown(f"🔗 **[{fp.get('title','')}]({fp.get('url','')})** — `Score: {fp.get('similarity',0):.2f}`")
            st.caption(f"Markdown код: `[{fp.get('title','')}]({fp.get('url','')})`")

# 4. GAP AUDIT
with tab4:
    st.subheader(f"📊 Аудит покрытия базы знаний для {selected_product}")
    audit_kw = st.text_input("Проверить поисковый запрос на слепые зоны", value=f"Can {selected_product} integrate with HubSpot?")
    if st.button("Провести аудит"):
        audit_facts = retrieve_facts(audit_kw, selected_product, top_k=3, threshold=0.0)
        if audit_facts:
            best_sc = audit_facts[0].get("similarity", 0)
            if best_sc > 0.65:
                st.success(f"Отличное покрытие! Score: {best_sc:.2f}")
            elif best_sc > 0.45:
                st.warning(f"Среднее покрытие ({best_sc:.2f}). Рекомендуется добавить точный факт.")
            else:
                st.error(f"Слепая зона ({best_sc:.2f})! В базе нет фактов.")
            for af in audit_facts:
                st.write(f"- {af.get('claim','')} *(Score: {af.get('similarity',0):.2f})*")
        else:
            st.error("Факты не найдены в базе.")

# 5. ИСТОРИЯ
with tab5:
    st.subheader("📜 История генераций")
    hist_data = get_content_history(selected_product)
    if hist_data:
        df_hist = pd.DataFrame(hist_data)
        st.dataframe(df_hist[["created_at", "author", "target_keyword", "content_type", "status"]])
        selected_id = st.selectbox("Открыть текст по ID:", df_hist["id"].tolist())
        row = next(r for r in hist_data if r["id"] == selected_id)
        st.markdown(f"### {row['target_keyword']}")
        st.markdown(row["generated_text"])
        st.info(f"**Вердикт Доктора:** {row.get('doctor_verdict','')}")
    else:
        st.info("История пока пуста.")
