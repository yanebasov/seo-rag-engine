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

# --- CUSTOM CSS (SaaS UI) ---
st.markdown("""
<style>
    /* Сайдбар и меню навигации */
    .stRadio div[role="radiogroup"] > label {
        background-color: transparent;
        padding: 10px 15px;
        border-radius: 8px;
        margin-bottom: 4px;
        transition: background-color 0.2s ease;
        cursor: pointer;
    }
    .stRadio div[role="radiogroup"] > label:hover {
        background-color: #f0f2f6;
    }
    /* Цветные бейджи для скора и статусов */
    .badge-green {
        background-color: #e6f4ea;
        color: #1e8e3e;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.85em;
        font-weight: 600;
        margin-left: 8px;
    }
    .badge-yellow {
        background-color: #fef7e0;
        color: #b06000;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.85em;
        font-weight: 600;
        margin-left: 8px;
    }
    .badge-red {
        background-color: #fce8e6;
        color: #d93025;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.85em;
        font-weight: 600;
        margin-left: 8px;
    }
    .badge-neutral {
        background-color: #f1f3f4;
        color: #5f6368;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.85em;
        font-weight: 600;
        margin-left: 8px;
    }
    /* Кастомные заголовки */
    h1, h2, h3 {
        color: #202124;
        font-weight: 600 !important;
    }
</style>
""", unsafe_allow_html=True)

# Функция для рендеринга бейджей
def get_score_badge(score):
    if score >= 0.65:
        return f"<span class='badge-green'>Score: {score:.2f}</span>"
    elif score >= 0.45:
        return f"<span class='badge-yellow'>Score: {score:.2f}</span>"
    else:
        return f"<span class='badge-red'>Score: {score:.2f}</span>"

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
    st.session_state["username"] = None

if not st.session_state["authenticated"]:
    with st.container(border=True):
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

# --- САЙДБАР (SaaS Style Navigation) ---
with st.sidebar:
    st.markdown(f"👤 **Пользователь:** <span class='badge-neutral'>{st.session_state['username']}</span>", unsafe_allow_html=True)
    if st.button("🚪 Выйти", use_container_width=True):
        st.session_state["authenticated"] = False
        st.session_state["username"] = None
        st.rerun()
    
    st.divider()
    
    st.markdown("<p style='color:#5f6368; font-size:0.8em; font-weight:700; letter-spacing:1px; margin-bottom:0px;'>MODULES</p>", unsafe_allow_html=True)
    
    menu = st.radio(
        "Навигация",
        options=[
            "✍️ Генерация + Доктор",
            "📊 Gap Audit",
            "⚙️ Data Manager (Sitemap & Playbooks)",
            "🔗 Линк-билдер (Векторный поиск)",
            "⚡ Batch (Пакетная генерация)",
            "📜 История"
        ],
        label_visibility="collapsed"
    )
    
    st.divider()
    
    st.markdown("<p style='color:#5f6368; font-size:0.8em; font-weight:700; letter-spacing:1px; margin-bottom:0px;'>SETTINGS</p>", unsafe_allow_html=True)
    selected_product = st.selectbox(
        "Продукт",
        options=["pics.io", "toriut"],
        format_func=lambda x: "Pics.io (DAM)" if x == "pics.io" else "Toriut (PIM)",
        label_visibility="collapsed"
    )
    
    gemini_key_input = st.text_input("Gemini API Key", value=DEFAULT_GEMINI_KEY, type="password")
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

            embed_m = None
            for pref in ["text-embedding-004", "embedding-001", "gemini-embedding"]:
                for c in embed_cands:
                    if pref in c: embed_m = c; break
                if embed_m: break
            if not embed_m and embed_cands: embed_m = embed_cands[0]

            gen_m = None
            for pref in ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.0-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
                for c in gen_cands:
                    if pref in c: gen_m = c; break
                if gen_m: break
            
            if not gen_m:
                for c in gen_cands:
                    if "flash" in c: gen_m = c; break

            if not gen_m and gen_cands: gen_m = gen_cands[0]

            return embed_m or "models/text-embedding-004", gen_m or "models/gemini-1.5-flash", "OK"
        else:
            return None, None, f"Код ошибки: {res.status_code}"
    except Exception as e:
        return "models/text-embedding-004", "models/gemini-1.5-flash", f"Fallback: {e}"

EMBED_MODEL, GEN_MODEL, KEY_STATUS = resolve_models(CURRENT_KEY)

with st.sidebar:
    if KEY_STATUS == "OK":
        st.markdown(f"""
        <div style='background-color: #f8f9fa; padding: 10px; border-radius: 8px; border: 1px solid #e0e0e0; font-size: 0.85em;'>
            <span style='color: #1e8e3e;'>●</span> <b>Connected</b><br>
            <span style='color: #5f6368;'>Search:</span> {EMBED_MODEL.replace('models/', '')}<br>
            <span style='color: #5f6368;'>Gen:</span> {GEN_MODEL.replace('models/', '')}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.error(f"⚠️ {KEY_STATUS}")

# --- API ФУНКЦИИ ---
def get_supabase_headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

def get_embedding(text: str):
    if not CURRENT_KEY or not EMBED_MODEL: return None
    url = f"https://generativelanguage.googleapis.com/v1beta/{EMBED_MODEL}:embedContent?key={CURRENT_KEY}"
    payload = {"content": {"parts": [{"text": text}]}}
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200: return res.json()["embedding"]["values"][:768]
    except Exception: pass
    return None

def generate_llm(prompt: str, temperature: float = 0.2):
    if not CURRENT_KEY or not GEN_MODEL: return "Ошибка: отсутствует Gemini API Key."
    url = f"https://generativelanguage.googleapis.com/v1beta/{GEN_MODEL}:generateContent?key={CURRENT_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": temperature}}
    try:
        res = requests.post(url, json=payload, timeout=30)
        if res.status_code == 200: return res.json()["candidates"][0]["content"]["parts"][0]["text"]
        return f"⚠️ Ошибка API Google ({res.status_code}): {res.json().get('error', {}).get('message', res.text)}"
    except Exception as e: return f"⚠️ Системная ошибка запроса: {e}"

def retrieve_facts(query: str, product: str, top_k: int = 6, threshold: float = 0.0):
    vec = get_embedding(query)
    if not vec: return []
    try:
        res = requests.post(f"{SUPABASE_URL}/rest/v1/rpc/match_facts", headers=get_supabase_headers(), json={"query_embedding": vec, "match_threshold": threshold, "match_count": top_k, "filter_product": product}, timeout=10)
        if res.status_code == 200: return res.json()
    except Exception: pass
    return []

def retrieve_linking_pages(query: str, product: str, top_k: int = 4, threshold: float = 0.0):
    vec = get_embedding(query)
    if not vec: return []
    try:
        res = requests.post(f"{SUPABASE_URL}/rest/v1/rpc/match_site_pages", headers=get_supabase_headers(), json={"query_embedding": vec, "match_threshold": threshold, "match_count": top_k, "filter_product": product}, timeout=10)
        if res.status_code == 200: return res.json()
    except Exception: pass
    return []

def save_generation_to_history(product, author, kw, content_type, text, verdict):
    try:
        requests.post(f"{SUPABASE_URL}/rest/v1/content_history", headers={**get_supabase_headers(), "Prefer": "return=minimal"}, json={"product": product, "author": author, "target_keyword": kw, "content_type": content_type, "generated_text": text, "doctor_verdict": verdict, "status": "PASS" if "PASS" in str(verdict).upper() else "FAIL"}, timeout=8)
    except Exception: pass

def get_content_history(product: str):
    try:
        res = requests.get(f"{SUPABASE_URL}/rest/v1/content_history?product=eq.{product}&order=created_at.desc&limit=20", headers=get_supabase_headers(), timeout=8)
        if res.status_code == 200: return res.json()
    except Exception: pass
    return []

# --- MAIN CONTENT AREA ---
st.title(menu.split(" (")[0])

# 1. ГЕНЕРАЦИЯ + ДОКТОР
if menu.startswith("✍️ Генерация"):
    with st.container(border=True):
        st.markdown("#### SEO параметры")
        col1, col2 = st.columns([1, 1])
        with col1:
            target_kw = st.text_input("Целевой ключевой запрос", value="Google Drive DAM integration features")
        with col2:
            content_type = st.selectbox("Тип контента", ["Feature Landing Page", "SEO Article Section", "Meta Title + Description + FAQ"])
        
        c1, c2 = st.columns(2)
        with c1: top_k = st.slider("Количество фактов из базы", 2, 12, 6)
        with c2: top_links_count = st.slider("Количество внутренних ссылок", 1, 6, 3)
        run_btn = st.button("🚀 Сгенерировать контент", type="primary")

    if run_btn and target_kw:
        st.divider()
        with st.spinner("Сбор данных из векторной базы..."):
            facts = retrieve_facts(target_kw, selected_product, top_k=top_k)
            pages = retrieve_linking_pages(target_kw, selected_product, top_k=top_links_count)
            
        c_left, c_right = st.columns([1.2, 2])
        
        with c_left:
            with st.container(border=True):
                st.markdown(f"**📚 Извлеченные факты ({len(facts)})**")
                if not facts: st.warning("Факты не найдены.")
                for f in facts:
                    st.markdown(f"- **[{f.get('category','').upper()}]** {f.get('claim','')} {get_score_badge(f.get('similarity', 0))}", unsafe_allow_html=True)
            
            with st.container(border=True):
                st.markdown(f"**🔗 Страницы для перелинковки ({len(pages)})**")
                if not pages: st.info("Страницы еще не загружены в базу.")
                for p in pages:
                    st.markdown(f"- [{p.get('title','')}]({p.get('url','')}) {get_score_badge(p.get('similarity', 0))}", unsafe_allow_html=True)

        if facts:
            with c_right:
                with st.container(border=True):
                    st.markdown("#### ✨ Результат генерации")
                    with st.spinner("Генерация текста с внедрением ссылок..."):
                        facts_context = "\n".join([f"- [{f.get('category','')}] {f.get('claim','')}" for f in facts])
                        links_context = "\n".join([f"- [{p.get('title','')}]({p.get('url','')})" for p in pages]) if pages else "Внутренние ссылки отсутствуют"
                        
                        gen_prompt = f"""
Ты — профессиональный B2B SaaS SEO-копирайтер для {selected_product}.
Напиши {content_type} под поисковый запрос "{target_kw}".
СТРОГИЕ ПРАВИЛА:
1. Используй ТОЛЬКО факты из базы ниже.
2. Органично вставь в текст 2-3 релевантных внутренних ссылки из блока СТРАНИЦЫ в виде Markdown [Анкор](url).
ФАКТЫ:\n{facts_context}\nСТРАНИЦЫ ДЛЯ ПЕРЕЛИНКОВКИ:\n{links_context}"""
                        generated_text = generate_llm(gen_prompt, temperature=0.2)
                        st.markdown(generated_text)

                with st.container(border=True):
                    st.markdown("#### 🩺 Аудит агентом «Доктор»")
                    with st.spinner("Проверка на галлюцинации..."):
                        doc_prompt = f"Проверь текст на соответствие фактам:\nФАКТЫ:\n{facts_context}\nТЕКСТ:\n{generated_text}\nВердикт: Есть галлюцинации? Статус: PASS или FAIL."
                        doc_verdict = generate_llm(doc_prompt, temperature=0.0)
                        
                        if "PASS" in doc_verdict.upper():
                            st.success(doc_verdict)
                        else:
                            st.error(doc_verdict)
                        save_generation_to_history(selected_product, st.session_state["username"], target_kw, content_type, generated_text, doc_verdict)

# 2. GAP AUDIT
elif menu.startswith("📊 Gap"):
    with st.container(border=True):
        st.markdown("#### Параметры аудита")
        audit_kw = st.text_input("Проверить поисковый запрос на слепые зоны", value=f"Can {selected_product} integrate with HubSpot?")
        run_audit = st.button("🔍 Провести аудит", type="primary")

    if run_audit:
        with st.spinner("Анализ векторной базы и структуры сайта..."):
            audit_facts = retrieve_facts(audit_kw, selected_product, top_k=3, threshold=0.0)
            pages_to_update = retrieve_linking_pages(audit_kw, selected_product, top_k=4)
            
            if audit_facts:
                best_sc = audit_facts[0].get("similarity", 0)
                
                # Кастомная плашка статуса
                if best_sc > 0.65:
                    st.markdown(f"<div style='background-color:#e6f4ea; padding:15px; border-radius:8px; border-left: 5px solid #1e8e3e;'><b>🟢 Отличное покрытие базы знаний!</b> Максимальная близость: {best_sc:.2f}</div><br>", unsafe_allow_html=True)
                elif best_sc > 0.45:
                    st.markdown(f"<div style='background-color:#fef7e0; padding:15px; border-radius:8px; border-left: 5px solid #b06000;'><b>🟡 Среднее покрытие.</b> Факты найдены, но могут быть слишком общими (Близость: {best_sc:.2f}).</div><br>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div style='background-color:#fce8e6; padding:15px; border-radius:8px; border-left: 5px solid #d93025;'><b>🔴 Слепая зона.</b> Прямых фактов нет (Близость: {best_sc:.2f}). Требуется актуализация.</div><br>", unsafe_allow_html=True)

                c1, c2 = st.columns([1, 1.2])
                with c1:
                    with st.container(border=True):
                        st.markdown("**Найденные факты в базе:**")
                        facts_text = ""
                        for af in audit_facts:
                            st.markdown(f"- {af.get('claim','')} {get_score_badge(af.get('similarity',0))}", unsafe_allow_html=True)
                            facts_text += f"- {af.get('claim','')}\n"
                with c2:
                    with st.container(border=True):
                        st.markdown("**Ближайшие страницы сайта (Кандидаты на обновление):**")
                        pages_text = ""
                        if pages_to_update:
                            for pu in pages_to_update:
                                st.markdown(f"- [{pu.get('title', 'Без названия')}]({pu.get('url', '')}) {get_score_badge(pu.get('similarity',0))}", unsafe_allow_html=True)
                                pages_text += f"- [{pu.get('title', 'Без названия')}]({pu.get('url', '')})\n"
                        else:
                            st.info("Подходящих страниц не найдено.")
                            pages_text = "Подходящих страниц не найдено."

                with st.container(border=True):
                    st.markdown("#### 🕵️ Пруфы аудита (Анализ от AI-стратега)")
                    with st.spinner("LLM анализирует нехватку данных..."):
                        proof_prompt = f"""
                        Ты контент-стратег для {selected_product}.
                        SEO-специалист проверяет интент: "{audit_kw}".
                        Найдены фрагменты в базе:\n{facts_text}
                        Релевантные страницы сайта:\n{pages_text}
                        Напиши аудит-пруф:
                        1. **Вердикт:** Хватит ли этого для статьи или будет "вода"?
                        2. **Missing Info:** Что нужно срочно задокументировать?
                        3. **Где актуализировать инфу:** Посоветуй 1-2 страницы из списка для размещения недостающих фактов (укажи почему).
                        """
                        st.info(generate_llm(proof_prompt, temperature=0.3))
            else:
                st.error("Факты не найдены в базе вообще. Это абсолютная слепая зона.")

# 3. DATA MANAGER
elif menu.startswith("⚙️ Data"):
    col_maps, col_playbooks = st.columns([1, 1])
    
    with col_maps:
        with st.container(border=True):
            st.markdown("#### 🌐 Мониторинг Sitemap")
            st.caption("Парсинг сайтмапов для отслеживания новых лендингов и обновления старых страниц.")
            
            st.markdown("<p style='font-size:0.9em;'><b>💡 Быстрый парсинг:</b></p>", unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            btn_pics = c1.button("🚀 pics.io", use_container_width=True)
            btn_bpics = c1.button("🚀 blog.pics.io", use_container_width=True)
            btn_toriut = c2.button("🚀 toriut.com", use_container_width=True)
            btn_btoriut = c2.button("🚀 blog.toriut.com", use_container_width=True)
            
            target_sitemap = st.text_input("Или введите вручную URL Sitemap:", value="https://pics.io/sitemap.xml")
            btn_manual = st.button("🔍 Спарсить введенный", type="primary", use_container_width=True)
            
            active_sitemap = None
            if btn_pics: active_sitemap = "https://pics.io/sitemap.xml"
            elif btn_bpics: active_sitemap = "https://blog.pics.io/sitemap.xml"
            elif btn_toriut: active_sitemap = "https://toriut.com/sitemap.xml"
            elif btn_btoriut: active_sitemap = "https://blog.toriut.com/sitemap.xml"
            elif btn_manual and target_sitemap: active_sitemap = target_sitemap.strip()
            
            if active_sitemap:
                with st.spinner(f"Чтение {active_sitemap}..."):
                    try:
                        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 'Accept': 'application/xml, text/xml, */*; q=0.01'}
                        r = requests.get(active_sitemap, headers=headers, timeout=20)
                        r.raise_for_status()
                        root = ET.fromstring(r.content)
                        for elem in root.iter():
                            if '}' in elem.tag: elem.tag = elem.tag.split('}', 1)[1]
                        
                        results = []
                        if root.tag == 'sitemapindex':
                            for s in root.findall('sitemap'): results.append({"Тип": "Индекс", "URL": s.findtext('loc', '-'), "Обновлено": s.findtext('lastmod', '-')})
                        elif root.tag == 'urlset':
                            for u in root.findall('url'): results.append({"Тип": "Страница", "URL": u.findtext('loc', '-'), "Обновлено": u.findtext('lastmod', '-')})
                        
                        if results:
                            df_sitemap = pd.DataFrame(results).sort_values(by="Обновлено", ascending=False)
                            st.success(f"Найдено ссылок: {len(results)}")
                            st.dataframe(df_sitemap, use_container_width=True, hide_index=True)
                        else: st.warning("Ссылок (<loc>) не найдено.")
                    except Exception as e: st.error(f"Ошибка: {e}")

    with col_playbooks:
        with st.container(border=True):
            st.markdown("#### 🚀 Плейбуки новых лендингов (Reverse Linking)")
            st.caption("Поиск мест для ссылок на еще неопубликованные страницы.")
            
            new_url = st.text_input("URL новой страницы (опционально)", placeholder="https://pics.io/new-feature")
            new_keywords = st.text_input("Главные ключевые слова", placeholder="AI search, face recognition")
            playbook_text = st.text_area("Текст плейбука / Описание", height=120, placeholder="Скопируйте сюда бриф фичи...")
            uploaded_playbook = st.file_uploader("Или загрузите текстовый файл (.txt, .md)", type=["txt", "md"])
            
            if st.button("🧠 Найти места для размещения", type="primary", use_container_width=True):
                final_text = playbook_text.strip()
                if uploaded_playbook: final_text += "\n\n" + uploaded_playbook.read().decode("utf-8")
                final_text = final_text.strip()

                if final_text:
                    with st.spinner("Анализ базы..."):
                        candidates = retrieve_linking_pages(final_text, selected_product, top_k=3)
                        if candidates:
                            for c in candidates:
                                with st.container(border=True):
                                    st.markdown(f"**🔗 Страница:** [{c.get('title', 'URL')}]({c.get('url', '')}) {get_score_badge(c.get('similarity', 0))}", unsafe_allow_html=True)
                                    target_link = new_url.strip() if new_url.strip() else "[URL_БУДЕТ_ЗДЕСЬ]"
                                    prompt = f"SEO-стратег для {selected_product}. Мы готовим новую страницу по теме:\n{new_keywords}\nБриф:\n{final_text}\nМы хотим поставить на нее ссылку со старой страницы ({c.get('url', '')}). Напиши 1-2 органичных предложения для добавления на эту старую страницу. Формат ссылки Markdown: [Анкор]({target_link})."
                                    st.info(generate_llm(prompt, temperature=0.3))
                        else: st.warning("Релевантных страниц не найдено.")
                else: st.error("Пожалуйста, добавьте текст плейбука.")

# 4. ЛИНК-БИЛДЕР (ВЕКТОРНЫЙ ПОИСК)
elif menu.startswith("🔗 Линк"):
    with st.container(border=True):
        st.markdown("#### 🔗 Векторный подбор страниц сайта (Internal Link Finder)")
        search_link_kw = st.text_input("Тема для подбора URL", value="Digital Asset Management for eCommerce")
        if st.button("Найти URL для перелинковки", type="primary"):
            found_pages = retrieve_linking_pages(search_link_kw, selected_product, top_k=8)
            if not found_pages:
                st.info("Страницы перелинковки еще не загружены.")
            for fp in found_pages:
                with st.container(border=True):
                    st.markdown(f"**[{fp.get('title','')}]({fp.get('url','')})** {get_score_badge(fp.get('similarity',0))}", unsafe_allow_html=True)
                    st.code(f"[{fp.get('title','')}]({fp.get('url','')})", language="markdown")

# 5. ПАКЕТНАЯ ГЕНЕРАЦИЯ
elif menu.startswith("⚡ Batch"):
    with st.container(border=True):
        st.markdown("#### ⚡ Пакетная генерация")
        batch_input = st.text_area("Список ключевых слов (по одному на строку)", height=140, value="Google Drive DAM integration\nShopify PIM catalog sync")
        batch_type = st.selectbox("Формат вывода", ["Meta Title + Description + FAQ", "SEO Article Section", "Feature Landing Page"])
        
        if st.button("🚀 Запустить пакетную обработку", type="primary"):
            keywords = [k.strip() for k in batch_input.split("\n") if k.strip()]
            results = []
            bar = st.progress(0)
            for i, kw in enumerate(keywords):
                facts = retrieve_facts(kw, selected_product, top_k=4)
                pages = retrieve_linking_pages(kw, selected_product, top_k=2)
                facts_txt = "\n".join([f"- {f.get('claim','')}" for f in facts])
                links_txt = "\n".join([f"- [{p.get('title','')}]({p.get('url','')})" for p in pages])
                prompt = f"Напиши {batch_type} для {selected_product} по теме '{kw}'. Факты:\n{facts_txt}\nСсылки:\n{links_txt}"
                txt = generate_llm(prompt)
                results.append({"Keyword": kw, "Generated_Content": txt, "Links": ", ".join([p.get('url','') for p in pages])})
                bar.progress((i + 1) / len(keywords))
            
            df_res = pd.DataFrame(results)
            st.dataframe(df_res, hide_index=True, use_container_width=True)
            st.download_button("📥 Скачать CSV", data=df_res.to_csv(index=False).encode('utf-8'), file_name=f"batch_{selected_product}.csv", mime="text/csv")

# 6. ИСТОРИЯ
elif menu.startswith("📜 История"):
    with st.container(border=True):
        st.markdown("#### 📜 История генераций")
        hist_data = get_content_history(selected_product)
        if hist_data:
            df_hist = pd.DataFrame(hist_data)
            st.dataframe(df_hist[["created_at", "author", "target_keyword", "content_type", "status"]], hide_index=True, use_container_width=True)
            
            selected_id = st.selectbox("Открыть лог (ID):", df_hist["id"].tolist())
            row = next(r for r in hist_data if r["id"] == selected_id)
            with st.container(border=True):
                st.markdown(f"**Keyword:** {row['target_keyword']}")
                st.divider()
                st.markdown(row["generated_text"])
                st.divider()
                st.markdown(f"**Вердикт Доктора:**")
                st.info(row.get('doctor_verdict',''))
        else:
            st.info("История пока пуста.")
