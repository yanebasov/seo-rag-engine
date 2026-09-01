import os
import json
import re
import xml.etree.ElementTree as ET
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

# --- САЙДБАР ---
with st.sidebar:
    st.success(f"👤 Пользователь: **{st.session_state['username']}**")
    if st.button("🚪 Выйти"):
        st.session_state["authenticated"] = False
        st.session_state["username"] = None
        st.rerun()
    st.divider()
    selected_product = st.selectbox(
        "🏢 Продукт:",
        options=["pics.io", "toriut"],
        format_func=lambda x: "Pics.io (DAM)" if x == "pics.io" else "Toriut (PIM)"
    )
    st.divider()
    gemini_key_input = st.text_input("🔑 Gemini API Key:", value=DEFAULT_GEMINI_KEY, type="password")

CURRENT_KEY = gemini_key_input.strip().strip("'").strip('"')

# Точный автодетект моделей
@st.cache_data(ttl=3600, show_spinner=False)
def resolve_models(api_key):
    if not api_key:
        return None, None, "Укажите Gemini API Key"
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        res = requests.get(url, timeout=6)
        if res.status_code == 200:
            models_data = res.json().get("models", [])
            embed_cands = [m["name"] for m in models_data if "embedContent" in m.get("supportedGenerationMethods", [])]
            gen_cands = [m["name"] for m in models_data if "generateContent" in m.get("supportedGenerationMethods", [])]

            # Подбор эмбеддингов
            embed_m = None
            for pref in ["text-embedding-004", "embedding-001", "gemini-embedding"]:
                for c in embed_cands:
                    if pref in c:
                        embed_m = c
                        break
                if embed_m:
                    break
            if not embed_m and embed_cands:
                embed_m = embed_cands[0]

            # Подбор генератора (приоритет 2.0-flash / 1.5-flash)
            gen_m = None
            for pref in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]:
                for c in gen_cands:
                    if pref in c:
                        gen_m = c
                        break
                if gen_m:
                    break
            if not gen_m:
                for c in gen_cands:
                    if "1.5" in c or "2.0" in c:
                        gen_m = c
                        break
            if not gen_m and gen_cands:
                gen_m = gen_cands[0]

            return embed_m or "models/text-embedding-004", gen_m or "models/gemini-1.5-flash", "OK"
        else:
            return None, None, f"Код ошибки: {res.status_code}"
    except Exception as e:
        return "models/text-embedding-004", "models/gemini-1.5-flash", f"Fallback: {e}"

EMBED_MODEL, GEN_MODEL, KEY_STATUS = resolve_models(CURRENT_KEY)

with st.sidebar:
    if KEY_STATUS == "OK":
        st.caption(f"🟢 **Подключено**\n\n- Поиск: `{EMBED_MODEL.replace('models/', '')}`\n- Генератор: `{GEN_MODEL.replace('models/', '')}`")
    else:
        st.error(f"⚠️ {KEY_STATUS}")

def get_supabase_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

def get_embedding(text: str):
    if not CURRENT_KEY or not EMBED_MODEL:
        st.error("Gemini API Key не настроен.")
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/{EMBED_MODEL}:embedContent?key={CURRENT_KEY}"
    payload = {"content": {"parts": [{"text": text}]}}
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            return res.json()["embedding"]["values"][:768]
        st.error(f"Google Embeddings Error ({res.status_code}): {res.text}")
    except Exception as e:
        st.error(f"Ошибка получения вектора: {e}")
    return None

def generate_llm(prompt: str, temperature: float = 0.2):
    if not CURRENT_KEY or not GEN_MODEL:
        return "Ошибка: отсутствует Gemini API Key."

    url = f"https://generativelanguage.googleapis.com/v1beta/{GEN_MODEL}:generateContent?key={CURRENT_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature}
    }
    try:
        res = requests.post(url, json=payload, timeout=30)
        if res.status_code == 200:
            return res.json()["candidates"][0]["content"]["parts"][0]["text"]
        st.error(f"Google LLM Error ({res.status_code}): {res.text}")
    except Exception as e:
        st.error(f"Ошибка вызова LLM: {e}")
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
    except Exception:
        pass
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

# --- ВКЛАДКИ ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "✍️ Генерация + Доктор",
    "⚡ Batch",
    "🔗 Линк-билдер",
    "📊 Gap Audit",
    "📜 История",
    "⚙️ Data Manager"
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

# 6. DATA MANAGER (УПРАВЛЕНИЕ БАЗОЙ И ПЛЕЙБУКАМИ)
with tab6:
    st.subheader("⚙️ Управление базой знаний и мониторинг актуальности")
    
    col_maps, col_playbooks = st.columns([1, 1])
    
    with col_maps:
        st.markdown("#### 🌐 Мониторинг Sitemap")
        st.caption("Парсинг сайтмапов для отслеживания новых лендингов и обновления старых страниц (по lastmod).")
        
        st.markdown("**💡 Быстрый парсинг (нажмите для запуска):**")
        c1, c2 = st.columns(2)
        btn_pics = c1.button("🚀 pics.io")
        btn_bpics = c1.button("🚀 blog.pics.io")
        btn_toriut = c2.button("🚀 toriut.com")
        btn_btoriut = c2.button("🚀 blog.toriut.com")
        
        st.markdown("**Или введите вручную:**")
        target_sitemap = st.text_input("URL Sitemap:", value="https://pics.io/sitemap.xml", label_visibility="collapsed")
        btn_manual = st.button("🔍 Спарсить введенный", type="primary")
        
        # Определяем, какой Sitemap парсить
        active_sitemap = None
        if btn_pics: active_sitemap = "https://pics.io/sitemap.xml"
        elif btn_bpics: active_sitemap = "https://blog.pics.io/sitemap.xml"
        elif btn_toriut: active_sitemap = "https://toriut.com/sitemap.xml"
        elif btn_btoriut: active_sitemap = "https://blog.toriut.com/sitemap.xml"
        elif btn_manual and target_sitemap: active_sitemap = target_sitemap.strip()
        
        if active_sitemap:
            with st.spinner(f"Чтение {active_sitemap}..."):
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Accept': 'application/xml, text/xml, */*; q=0.01'
                    }
                    r = requests.get(active_sitemap, headers=headers, timeout=20)
                    r.raise_for_status()
                    
                    root = ET.fromstring(r.content)
                    
                    # Универсальная очистка XML-дерева от неймспейсов
                    for elem in root.iter():
                        if '}' in elem.tag:
                            elem.tag = elem.tag.split('}', 1)[1]
                    
                    results = []
                    if root.tag == 'sitemapindex':
                        for s in root.findall('sitemap'):
                            loc = s.findtext('loc', default='-')
                            lm = s.findtext('lastmod', default='-')
                            results.append({"Тип": "Индекс", "URL": loc, "Последнее обновление": lm})
                    elif root.tag == 'urlset':
                        for u in root.findall('url'):
                            loc = u.findtext('loc', default='-')
                            lm = u.findtext('lastmod', default='-')
                            results.append({"Тип": "Страница", "URL": loc, "Последнее обновление": lm})
                    
                    if results:
                        df_sitemap = pd.DataFrame(results)
                        df_sitemap = df_sitemap.sort_values(by="Последнее обновление", ascending=False)
                        st.success(f"Найдено ссылок: {len(results)}")
                        st.dataframe(df_sitemap, use_container_width=True)
                        st.info("💡 Следующий шаг архитектуры: Настроить крон-триггер, который берет свежие URL из этой таблицы, скрапит их HTML, разбивает на H2/H3 блоки, делает новые эмбеддинги и пушит в таблицу site_pages в Supabase.")
                    else:
                        st.warning("Сайтмап распарсился, но ссылок (<loc>) внутри не найдено.")
                        
                except Exception as e:
                    st.error(f"Ошибка парсинга или недоступность сайта: {e}")

    with col_playbooks:
        st.markdown("#### 🚀 Плейбуки новых лендингов (Reverse Linking)")
        st.caption("Загрузите бриф новой страницы, чтобы система нашла места на старых страницах сайта, куда можно органично вписать ссылку на нее.")
        
        new_url = st.text_input("URL новой страницы", placeholder="https://pics.io/new-feature")
        new_keywords = st.text_input("Главные ключевые слова", placeholder="AI search, face recognition")
        playbook_text = st.text_area("Текст плейбука / Описание лендинга", height=120, placeholder="Скопируйте сюда бриф фичи, зачем она нужна и какую проблему решает...")
        
        if st.button("🧠 Найти места для размещения ссылок", type="primary"):
            if playbook_text and new_url:
                with st.spinner("Анализ плейбука и поиск релевантных страниц в базе..."):
                    candidates = retrieve_linking_pages(playbook_text, selected_product, top_k=3, threshold=0.0)
                    
                    if candidates:
                        st.success(f"Найдено {len(candidates)} подходящих страниц для размещения!")
                        
                        for c in candidates:
                            with st.expander(f"🔗 Размещение на: {c.get('title', 'Без названия')} (Score: {c.get('similarity', 0):.2f})", expanded=True):
                                st.markdown(f"**URL:** {c.get('url', '')}")
                                
                                inject_prompt = f"""
Ты SEO-стратег для {selected_product}. Мы выпустили новую страницу:
URL: {new_url}
Ключевые слова: {new_keywords}
Суть страницы (Плейбук): {playbook_text}

Мы хотим поставить на нее ссылку с нашей старой страницы:
URL старой страницы: {c.get('url', '')}
Тема старой страницы: {c.get('title', '')}

ЗАДАЧА:
Напиши 1-2 органичных предложения, которые мы можем ДОПИСАТЬ на старую страницу, чтобы логично сослаться на новую. 
Используй Markdown для ссылки: [Анкор]({new_url}). Анкор должен быть естественным и релевантным ключевым словам.
"""
                                recommendation = generate_llm(inject_prompt, temperature=0.3)
                                st.info("**Рекомендация по добавлению текста:**")
                                st.markdown(recommendation)
                    else:
                        st.warning("Не удалось найти релевантные страницы в базе. Возможно, тема слишком уникальна.")
            else:
                st.error("Укажите URL новой страницы и текст плейбука.")
