from pipeline.manager import pipeline_manager
import os, json, time, random, re, sys
import requests
import urllib.parse
import html as html_lib
from difflib import SequenceMatcher
try:
    from llama_cpp import Llama
except ImportError:
    Llama = None

# Architectural Modules (Session Isolation, Memory Architecture, Knowledge Router)
try:
    from session_manager import get_session_manager
    from memory_orchestrator import get_memory_orchestrator
    from knowledge_router import get_knowledge_router
    from telemetry_manager import get_telemetry_manager
    _telemetry_mgr = get_telemetry_manager()
except Exception as _arch_import_err:
    print(f"[conversation] Warning loading architecture modules: {_arch_import_err}")
    get_session_manager = None
    get_memory_orchestrator = None
# ML Cognition Classifier (Modular API)
try:
    import models.nlp.api as nlp_api
    from cognition_classifiers import get_cognition_classifier
    _cognition_ml = get_cognition_classifier()
    _nlp_ready = True
except (ImportError, Exception) as _cog_err:
    print(f"[conversation] Notice: could not load cognition classifier: {_cog_err}")
    _cognition_ml = None
    _nlp_ready = False

# ML Experience Replay (Self-Learning)
try:
    from evolution.experience_replay import get_experience_replay
    _experience_replay = get_experience_replay()
except ImportError:
    _experience_replay = None


# Reconfigure console streams to UTF-8 on import to prevent UnicodeEncodeErrors on Windows
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
except Exception as _err:
    print(f"[conversation.py] Silenced exception: {_err}")

# ===============================
# SHARED PATHS
# ===============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EMOTION_TXT = os.path.join(BASE_DIR, "shared", "emotion.txt")

def _read_emotion():
    """Read current emotion label from shared/emotion.txt. Returns 'neutral' on failure."""
    try:
        if os.path.exists(EMOTION_TXT):
            with open(EMOTION_TXT, "r", encoding="utf-8") as f:
                val = f.read().strip()
                return val if val else "neutral"
    except Exception as _err:
        print(f"[conversation.py] Silenced exception: {_err}")
    return "neutral"

# ===============================
# DUCKDUCKGO SEARCH INTEGRATION (INTERNET INTELLIGENCE LAYER)
# ===============================
def search_duckduckgo(query):
    """
    Search via Universal Internet Intelligence Layer (InternetManager) with DuckDuckGo provider.
    Supports intelligent caching, offline fallback, rate-limiting, and direct HTML scraping.
    """
    if not query or len(query.strip()) < 2:
        return ""
    
    clean_query = query.strip()
    if _telemetry_mgr:
        _telemetry_mgr.log_event("Searching Started", details={"query": clean_query})

    
    # 1. Try Universal InternetManager orchestrator
    try:
        from internet import get_internet_manager
        im = get_internet_manager()
        res = im.search(clean_query)
        if res:
            return res
    except Exception as e_im:
        print(f"[DuckDuckGo] InternetManager delegation warning: {e_im}")

    # Fallback direct HTML scraping if InternetManager is not ready
    default_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.112 Safari/537.36"
    try:
        from config.config_manager import get_config_manager
        cfg = get_config_manager()
        ua = cfg.get("internet_intelligence.user_agent", default_ua)
    except Exception:
        ua = default_ua
    headers = {
        "User-Agent": ua,
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    # 1. Try python duckduckgo_search or ddgs library if installed
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(clean_query, max_results=3):
                    title = r.get("title", "")
                    snippet = r.get("body", "")
                    if snippet:
                        results.append(f"- {title}: {snippet}" if title else f"- {snippet}")
        if results:
            print(f"[DuckDuckGo] Retrieved {len(results)} results via DDGS library for '{clean_query}'")
            return "\n".join(results)
    except Exception as _err:
        print(f"[conversation.py] Silenced exception: {_err}")

    # 2. Try html.duckduckgo.com scraping
    try:
        try:
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            base_url = cfg.get("apis.duckduckgo_html", "https://html.duckduckgo.com/html/?q=")
            url = f"{base_url}{urllib.parse.quote(clean_query)}"
        except Exception:
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(clean_query)}"
        
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            html_text = r.text
            # Match result snippets
            snippets = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', html_text, re.DOTALL)
            if not snippets:
                snippets = re.findall(r'<td class="result-snippet"[^>]*>(.*?)</td>', html_text, re.DOTALL)
            results = []
            for s in snippets:
                clean_s = re.sub(r'<[^>]*>', '', s).strip()
                clean_s = html_lib.unescape(clean_s)
                if clean_s and len(clean_s) > 10:
                    results.append(f"- {clean_s}")
            if results:
                print(f"[DuckDuckGo] Retrieved {len(results)} results via HTML for '{clean_query}'")
                return "\n".join(results[:3])
    except Exception as e:
        print(f"[DuckDuckGo] HTML search error for '{clean_query}': {e}")

    # 3. Fallback to lite.duckduckgo.com
    try:
        try:
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            lite_url = cfg.get("apis.duckduckgo_lite", "https://lite.duckduckgo.com/lite/")
        except Exception:
            lite_url = "https://lite.duckduckgo.com/lite/"
        
        r_lite = requests.post(lite_url, data={"q": clean_query}, headers=headers, timeout=5)
        if r_lite.status_code == 200:
            html_lite = r_lite.text
            snippets = re.findall(r'<td class="result-snippet"[^>]*>(.*?)</td>', html_lite, re.DOTALL)
            results = []
            for s in snippets:
                clean_s = re.sub(r'<[^>]*>', '', s).strip()
                clean_s = html_lib.unescape(clean_s)
                if clean_s and len(clean_s) > 10:
                    results.append(f"- {clean_s}")
            if results:
                print(f"[DuckDuckGo] Retrieved {len(results)} results via Lite for '{clean_query}'")
                return "\n".join(results[:3])
    except Exception as e_lite:
        print(f"[DuckDuckGo] Lite search error for '{clean_query}': {e_lite}")

    return ""

def needs_search(text):
    l = text.lower()
    
    # Exclude companion-oriented personal queries
    personal_phrases = [
        "how are you", "how've you been", "do you like", "your favorite",
        "what do you think of me", "are you", "do you have", "can you tell me about yourself",
        "what are you doing", "what is your name", "who are you", "tell me about you"
    ]
    if any(p in l for p in personal_phrases):
        return False
        
    search_keywords = [
        "who is", "who was", "what is", "what was", "where is", "where was",
        "current", "latest", "today", "weather", "news", "price", "stock",
        "how many", "tell me about", "who won", "president", "prime minister",
        "definition of", "meaning of", "vs", "versus", "date today", "time today",
        "release date", "when did", "when is", "score of", "winner of",
        "capital of", "population of", "how high", "how deep", "how far",
        "distance between", "how old is", "birthday of", "height of", "who wrote",
        "who directed", "cast of", "movie release", "stands for", "acronym",
        "how to cook", "recipe for", "how do i make", "ingredients for",
        "recommend a", "recommend some", "best movie", "best book", "best game", "good anime",
        "top 10", "suggest a", "suggest some"
    ]
    
    if any(k in l for k in search_keywords):
        return True
        
    question_words = ["what", "where", "when", "who", "why", "how"]
    if "?" in text and any(l.strip().startswith(w) for w in question_words):
        informational_terms = ["recipe", "make", "cook", "history", "origin", "event", "news", "weather", "price", "show", "game", "book", "movie", "song", "artist"]
        if any(it in l for it in informational_terms):
            return True
            
    return False

# ===============================
# HEALTH PRIORITY ENGINE
# ===============================
def health_priority_engine(user, categories):
    """
    Parses user inputs for signs of starvation, lack of sleep, exhaustion,
    dehydration, fever, or vomiting dynamically using the LLM model or Fast ML,
    with zero hardcoding.
    """
    # Fast path: skip LLM for pure companion categories
    pure_companion = {"greeting", "compliment", "flirting", "intimacy", "teasing"}
    if categories and set(categories).issubset(pure_companion):
        return "NORMAL", []
        
    # ML Fast Path Layer (GPU NLP API)
    if _nlp_ready:
        ml_priority = nlp_api.predict_health_priority(user)
        if ml_priority in ["HIGH", "MEDIUM"]:
            print(f"[Cognition ML] Fast-tracked health priority to {ml_priority}")
            return ml_priority, [user] # Pass user text as symptom placeholder

    extraction_prompt = (
        "<|im_start|>system\n"
        "You are an AI medical/health analyzer. Analyze the user's message and extract the exact health issues, "
        "sickness symptoms, overwork/exhaustion (e.g. working long hours), starvation, dehydration, or lifestyle concerns mentioned in the text. Do not generalize.\n"
        "If there are no concerns, respond EXACTLY with: NONE\n"
        "If concerns exist, respond EXACTLY with: ISSUES: <comma-separated list of exact issues>\n"
        "<|im_end|>\n"
        f"<|im_start|>user\n{user}<|im_end|>\n"
        "<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )
    
    try:
        out = llm(
            extraction_prompt,
            max_tokens=60,
            temperature=0.1,
            stop=["<|im_end|>", "<|im_start|>"]
        )
        raw = out["choices"][0]["text"].strip()
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE).strip()
        raw = re.sub(r"</?think>", "", raw, flags=re.IGNORECASE).strip()
        
        if raw.upper().startswith("ISSUES:"):
            issues = [i.strip() for i in raw[7:].split(",") if i.strip()]
            if issues:
                # Classify priority dynamically: multiple issues or overload symptoms is HIGH
                priority = "HIGH" if len(issues) >= 2 or any(any(x in i.lower() for x in ["sleep", "fever", "vomit", "overload", "exhaust", "pain"]) for i in issues) else "MEDIUM"
                return priority, issues
    except Exception as e:
        print(f"Dynamic health priority engine error: {e}")
        
    return "NORMAL", []

# ===============================
# THE CONVERSATION DIRECTOR
# ===============================
def conversation_director(user, history, mem, categories):
    """
    Central cognitive controller for Vivy.
    Determines search need, health priority, and conversation goal prior to response.
    
    Returns a dict containing the planned cognitive parameters.
    """
    # 1. Analyze Health/Safety Priority
    health_priority, symptoms = health_priority_engine(user, categories)
    
    # 2. Determine Conversation Mode
    if health_priority in ["HIGH", "MEDIUM"]:
        conversation_mode = "health_priority"
    elif "health" in categories:
        conversation_mode = "health_priority"
        # Ensure health also triggers a search even if LLM extraction returned NORMAL
        if health_priority == "NORMAL":
            health_priority = "MEDIUM"
    elif mem.get("emotional_beat_active"):
        conversation_mode = "companion"
    elif mem.get("active_task") == "cooking" or mem.get("current_topic") == "recipes/cooking":
        # Only set recipe assistance if they are actually talking about food/recipes, or if they haven't started yet.
        # This prevents emotional/relationship follow-ups from getting trapped in cooking mode.
        food_words = ["recipe", "ingredients", "cook", "make", "burger", "pizza", "ramen", "pasta", "chicken", "food", "steps", "instructions", "prepare", "boil", "pan", "ingredient", "onion", "cheese", "bread"]
        if any(w in user.lower() for w in food_words) or "recipe" in categories:
            conversation_mode = "recipe assistance"
        else:
            conversation_mode = "companion"
    elif "recipe" in categories:
        conversation_mode = "recipe assistance"
    elif "food_need" in categories and mem.get("active_task") != "cooking":
        # Hungry but no recipe requested yet — stay in companion mode, ask warmly what they want
        conversation_mode = "companion"
    elif "recommendation" in categories:
        conversation_mode = "recommendations"
    elif "knowledge" in categories:
        conversation_mode = "information retrieval"
    elif "technical" in categories:
        conversation_mode = "technical assistance"
    else:
        conversation_mode = "companion"

    # Context inheritance: if the user sends a very short follow-up (like "really?" or "omg")
    # and recent history contains a health topic, inherit health-priority mode
    if conversation_mode == "companion" and len(user.split()) <= 4:
        recent_vivy = " ".join(
            t[6:] for t in history[-4:] if t.startswith("Vivy: ")
        ).lower()
        recent_user = " ".join(
            t[5:] for t in history[-4:] if t.startswith("You: ")
        ).lower()
        health_signals = ["dizzy","headache","fever","vomit","sick","nausea","pain","diarrhea","poop","faint","unwell","fatigue","stomach","cramps"]
        if any(sig in recent_user or sig in recent_vivy for sig in health_signals):
            conversation_mode = "health_continuation"
            health_priority = "MEDIUM"

    # 3. Coordinate DuckDuckGo Search Decision
    should_search = False
    search_query = ""
    ts = mem.get("task_state", {})
    
    # Override: do not search during clarification, empty-handed cooking, on hunger alone, or affirmatives
    is_clarification_or_empty = ts.get("needs_clarification") or ts.get("empty_handed")
    is_hunger_only = "food_need" in categories and not ("recipe" in categories or mem.get("active_task") == "cooking")
    is_affirmative_only = categories == ["affirmative"] or ("affirmative" in categories and len(categories) <= 2 and "casual" in categories)

    if is_clarification_or_empty or is_hunger_only or is_affirmative_only:
        should_search = False
        search_query = ""
    elif conversation_mode in ("health_priority", "health_continuation") and symptoms:
        should_search = True
        if len(symptoms) >= 2:
            search_query = f"{' and '.join(symptoms[:3])} together causes symptoms diagnosis treatment"
        else:
            search_query = f"{symptoms[0]} symptoms causes treatment natural remedy"
    elif conversation_mode == "health_priority" and not symptoms:
        # Health detected by classifier but LLM extraction missed — search anyway
        should_search = True
        search_query = f"{user} health symptoms causes treatment"
    elif conversation_mode == "recipe assistance":
        task_query = ts.get("query", "")
        query_term = task_query if task_query else user
        ql = query_term.lower()
        search_terms = ["best", "traditional", "authentic", "restaurant", "latest", "style", "kfc", "original", "famous"]
        if any(term in ql for term in search_terms) or not task_query:
            should_search = True
            search_query = f"{query_term} recipe ingredients instructions step by step"
        else:
            should_search = False
            search_query = ""
    else:
        # Fallback to autonomous search decision for other categories
        should_search, search_query = autonomous_search_decision(user, history, mem, categories)
        
    # 4. Reaction Planning
    reaction_type = "neutral"
    if "health" in categories or conversation_mode in ("health_priority", "health_continuation"):
        reaction_type = "comfort"
    elif "intimacy" in categories or "vulnerable" in categories or "comfort" in categories:
        reaction_type = "comfort"
    elif "teasing" in categories:
        reaction_type = "tease"
    elif "flirting" in categories:
        rel_score = mem.get("relationship", {}).get("score", 30)
        if rel_score < 50:
            reaction_type = "serious"
        else:
            reaction_type = "blush"
            
    # 5. Memory Coordination
    should_remember = False
    ranked_mem = rank_memories(user, mem)
    if ranked_mem:
        should_remember = True
        
    director_state = {
        "health_priority": health_priority,
        "symptoms": symptoms,
        "conversation_mode": conversation_mode,
        "should_search": should_search,
        "search_query": search_query,
        "reaction_type": reaction_type,
        "should_remember": should_remember,
        "memory_to_use": ranked_mem if should_remember else ""
    }
    
    print(f"Conversation Director Plan: {director_state}")
    return director_state

# ===============================
# AUTONOMOUS SEARCH DECISION ENGINE
# ===============================
def autonomous_search_decision(user, history, mem, categories):
    """LLM-driven autonomous search decision. Uses a compact prompt to determine
    if real-world web knowledge would genuinely improve Vivy's response, and
    generates an optimized search query if so.

    This replaces hardcoded keyword matching as the primary search trigger.
    The old needs_search() is preserved for backward compatibility and as a fallback.

    Returns (should_search: bool, search_query: str)
    """
    # Fast-path: skip the LLM call for pure companion interactions
    # that never benefit from web search (saves ~300ms per message)
    pure_companion = {
        "greeting", "farewell", "compliment", "flirting",
        "intimacy", "comfort", "teasing", "mystery"
    }
    active_cats = set(categories)
    if active_cats and active_cats.issubset(pure_companion):
        print("Autonomous Search: skipped (pure companion interaction)")
        return False, ""
        
    # ML Fast Path Layer
    if _cognition_ml is not None and _cognition_ml.is_ready:
        is_search = _cognition_ml.predict_search_intent(user)
        if is_search:
            print("[Cognition ML] Fast-tracked search intent to TRUE")
            return True, user

    # Build compact context for the decision LLM call
    recent = ""
    for msg in history[-3:]:
        recent += msg + "\n"

    active_topic = mem.get("current_topic", "general")
    temp_states = list(mem.get("temporary_states", {}).keys())

    decision_prompt = (
        "<|im_start|>system\n"
        "You are an AI cognitive director. Analyze the user's message to decide if searching the web (DuckDuckGo) "
        "would provide useful real-world facts, safety advice, or verify if their statement is safe, good, or bad.\n\n"
        "Search IS needed for: health/safety topics, lifestyle habits/choices, factual assertions/questions, recipes, "
        "recommendations, news, current events, technical assistance, product details.\n\n"
        "Search is NOT needed for: simple greetings, emotional companion comfort, relationship talk, compliments, simple chit-chat.\n\n"
        "If search is needed, respond EXACTLY with: SEARCH: <optimized 3-8 word search query>\n"
        "If search is not needed, respond EXACTLY with: NONE\n"
        "<|im_end|>\n"
    )

    decision_prompt += "<|im_start|>user\n"
    if recent.strip():
        decision_prompt += f"Recent conversation:\n{recent.strip()}\n\n"
    decision_prompt += f"Current message: {user}\n"
    if active_topic and active_topic != "general":
        decision_prompt += f"Topic: {active_topic}\n"
    if temp_states:
        decision_prompt += f"User states: {', '.join(temp_states)}\n"
    decision_prompt += "<|im_end|>\n"
    decision_prompt += "<|im_start|>assistant\n<think>\n\n</think>\n\n"

    try:
        out = llm(
            decision_prompt,
            max_tokens=25,
            temperature=0.1,
            stop=["<|im_end|>", "<|im_start|>", "\n\n"]
        )
        raw = out["choices"][0]["text"].strip()
        # Strip any leaked think blocks
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE).strip()
        raw = re.sub(r"</?think>", "", raw, flags=re.IGNORECASE).strip()

        print(f"Autonomous Search Decision: '{raw}'")

        if raw.upper().startswith("SEARCH:"):
            query = raw[7:].strip().strip('"\'')
            if query and len(query) > 2:
                return True, query
            else:
                return True, user
        else:
            return False, ""
    except Exception as e:
        print(f"Autonomous search decision error: {e}")
        # Fallback to legacy hardcoded needs_search
        if needs_search(user):
            return True, user
        return False, ""

# ===============================
# CONFIG
# ===============================
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "Qwen3-8B-Q4_K_M.gguf")
MEMORY_FILE = "vivy_memory.json"

_llm_instance = None

def get_llm():
    global _llm_instance
    if _llm_instance is None:
        if Llama is None:
            raise RuntimeError("llama_cpp module is not available in current environment.")
        _llm_instance = Llama(
            model_path=MODEL_PATH,
            # Context
            n_ctx=8192,
            # CPU
            n_threads=8,
            # Prompt evaluation
            n_batch=512,
            n_ubatch=512,
            # GPU
            n_gpu_layers=-1,
            offload_kqv=True,
            flash_attn=True,
            # Memory
            use_mmap=True,
            use_mlock=False,
            # Generation
            temperature=0.75,
            repeat_penalty=1.15,
            verbose=False,
        )
    return _llm_instance

class LazyLlamaProxy:
    def __call__(self, *args, **kwargs):
        return get_llm()(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(get_llm(), name)

llm = LazyLlamaProxy()

# ===============================
# PART 3 — MODEL & TOKEN BUDGET LIMITS
# ===============================
def get_model_limits():
    """Detect model size and context window from llama_cpp instance.
    Dynamically sizes system prompt and context length budget."""
    try:
        n_ctx = llm.n_ctx()
    except Exception:
        n_ctx = 768
    
    model_lower = getattr(llm, "model_path", "").lower()
    is_small_model = ("1b" in model_lower) or ("llama-3.2" in model_lower)
    
    # Scale token allocation budgets
    if n_ctx <= 768:
        max_history = 6
        prompt_verbosity = "compact"
    elif n_ctx <= 2048:
        max_history = 10
        prompt_verbosity = "standard"
    else:
        max_history = 16
        prompt_verbosity = "detailed"
        
    if is_small_model:
        prompt_verbosity = "compact"
        
    return {
        "max_history": max_history,
        "prompt_verbosity": prompt_verbosity,
        "n_ctx": n_ctx
    }

# ===============================
# PART 3 — ADAPTIVE TEMPERATURE ENGINE
# ===============================
def get_adaptive_temp(categories, user):
    """Determine dynamic temperature based on classification and reasoning patterns."""
    user_lower = user.lower()
    # Planning patterns
    if any(w in user_lower for w in ["plan", "todo", "schedule", "task", "organize", "list"]):
        return 0.3
    # Reasoning patterns
    if any(w in user_lower for w in ["why", "how", "explain", "because", "reason"]):
        return 0.35
        
    if "technical" in categories:
        return 0.2
    if "question" in categories:
        return 0.35  # reasoning/factual
    if "joke" in categories:
        return 0.95  # creative
    if "flirting" in categories:
        return 0.85  # warm/playful
    if "greeting" in categories:
        return 0.8
    if "farewell" in categories:
        return 0.8
    # Default casual
    return 0.75

# ===============================
# MEMORY
# ===============================
DEFAULT_MEMORY = {
    "name": None,
    "likes": [],
    "dislikes": [],
    "topics": {},
    "events": [],
    "summary": "",
    "style": {"humor": 0.6, "playful": 0.7},
    "tone": "neutral",
    "last_greeting": None,
    "last_user_time": None,
    "last_reply": "",
    "arc": {"topic": None, "stage": 0},
    # PART 2 — Relationship Engine (each dim 0-100)
    "relationship": {
        "trust": 30, "comfort": 30, "warmth": 35,
        "playfulness": 40, "familiarity": 20, "score": 30
    },
    # PART 2 — Emotion Vector (continuous, each 0-100)
    "emotion_vector": {
        "happiness": 60, "curiosity": 65, "confidence": 70,
        "playfulness": 65, "calmness": 75, "affection": 40,
        "embarrassment": 10
    },
    # PART 2 — Persistent mood label
    "mood": "relaxed",
    # PART 2 — Track last 5 reply opening words to prevent repetition
    "reply_openings": [],
    # PART 4 — Memory Layers
    "long_term_facts": {},     # Permanent details (name, job, preferences)
    "temporary_states": {},    # Decaying temporary states with timestamps
    # PART 6 — Intelligent Context Schema
    "summary": "",             # incremental conversation summary
    "current_topic": None,
    "subtopic": None,
    "topic_confidence": 0.0,
    "topics_list": [],         # multi-topic list
    "open_questions": [],      # open unanswered questions
    "promises": [],            # Vivy's promises
    # PART 7 — Multi-Agent Schema
    "planner_state": {
        "primary_goal": "socializing",
        "secondary_goal": "casual chat",
        "need_humor": False
    },
    "conversation_goal": "socializing",
    "interrupted_topics": [],   # topic restoration stack
    "conversation_count": 0,
    # PART 9 — Health Context Accumulator
    "active_symptoms": [],          # Grows each health turn, cleared on topic change
    "health_concern_level": 0,      # 0-10 escalation tracker, resets when health ends
    "last_director_mode": "companion",  # Tracks prior turn mode for emotional continuity
    # PART 10 — Dialogue State & Task Manager (DSM/TM)
    "active_task": "none",          # "none", "cooking", "health"
    "task_state": {
        "name": "",                 # "recipe", "symptoms"
        "query": "",                # exact query (e.g. "ramen")
        "queue": [],                # remaining foods queued after first
        "step": 0,                  # current turn step in the task
        "completed": False,
        "skip_prep": False,         # skip prep questions and go straight to recipe
        "needs_clarification": False,  # multi-recipe: ask which to start with
        "empty_handed": False       # user said they have nothing to cook with
    },
    # PART 11 — Response Complexity & Strategy Planner
    "strategy_plan": {
        "dialogue_mode": "Companion",  # Companion, Teacher, Chef, Doctor Helper, Programmer, Friend, Listener, Researcher, Planner, Coach
        "strategy": "medium",          # tiny, short, medium, long, tutorial, story, empathy, advice, humor
        "complexity": "simple",        # simple, detailed, comprehensive
        "ask_question": True
    }
}

def repair(mem):
    for k, v in DEFAULT_MEMORY.items():
        if k not in mem:
            import copy
            mem[k] = copy.deepcopy(v)
    if not isinstance(mem.get("topics"), dict):
        mem["topics"] = {}
    for k, v in DEFAULT_MEMORY["relationship"].items():
        mem["relationship"].setdefault(k, v)
    for k, v in DEFAULT_MEMORY["emotion_vector"].items():
        mem["emotion_vector"].setdefault(k, v)
    if not isinstance(mem.get("reply_openings"), list):
        mem["reply_openings"] = []
    if not isinstance(mem.get("long_term_facts"), dict):
        mem["long_term_facts"] = {}
    if not isinstance(mem.get("temporary_states"), dict):
        mem["temporary_states"] = {}
    if not isinstance(mem.get("open_questions"), list):
        mem["open_questions"] = []
    if not isinstance(mem.get("promises"), list):
        mem["promises"] = []
    if not isinstance(mem.get("topics_list"), list):
        mem["topics_list"] = []
    if not isinstance(mem.get("planner_state"), dict):
        mem["planner_state"] = copy.deepcopy(DEFAULT_MEMORY["planner_state"])
    if not isinstance(mem.get("interrupted_topics"), list):
        mem["interrupted_topics"] = []
    if not isinstance(mem.get("active_symptoms"), list):
        mem["active_symptoms"] = []
    if not isinstance(mem.get("health_concern_level"), int):
        mem["health_concern_level"] = 0
    if not isinstance(mem.get("last_director_mode"), str):
        mem["last_director_mode"] = "companion"
    if not isinstance(mem.get("active_task"), str):
        mem["active_task"] = "none"
    if not isinstance(mem.get("task_state"), dict):
        mem["task_state"] = copy.deepcopy(DEFAULT_MEMORY["task_state"])
    else:
        ts = mem["task_state"]
        ts.setdefault("skip_prep", False)
        ts.setdefault("queue", [])
        ts.setdefault("needs_clarification", False)
        ts.setdefault("empty_handed", False)
    if not isinstance(mem.get("strategy_plan"), dict):
        mem["strategy_plan"] = copy.deepcopy(DEFAULT_MEMORY["strategy_plan"])
    return mem

if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_MEMORY, f, indent=2, ensure_ascii=False)

def load():
    try:
        with open(MEMORY_FILE, encoding="utf-8") as f:
            mem = repair(json.load(f))
        # Fix 9d: Session isolation — reset active_task if last interaction was > 30 minutes ago
        last_time = mem.get("last_user_time", 0)
        if last_time and (time.time() - last_time) > 1800:  # 30 minutes
            mem["active_task"] = "none"
            mem["task_state"] = copy.deepcopy(DEFAULT_MEMORY["task_state"])
            mem["health_concern_level"] = 0
            mem["active_symptoms"] = []
        return mem
    except:
        return json.loads(json.dumps(DEFAULT_MEMORY))

def save(mem):
    tmp = MEMORY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(mem, f, indent=2, ensure_ascii=False)
    os.replace(tmp, MEMORY_FILE)

# ===============================
# TEXT UTILITIES
# ===============================
STOPWORDS = {
    "i","me","you","a","the","and","to","is","it","of","in","on",
    "for","with","that","this","are","was","be","so","do","did",
    "my","your","we","they"
}

# Fix #1 — Whisper noise/timestamp tokens that must never enter memory
_WHISPER_NOISE_TOKENS = {
    "blank_audio", "music", "laughter", "applause", "indistinct",
    "speaking", "foreign", "language", "upbeat", "sighs", "sigh",
    "silence", "noise", "static", "playing"
}
_WHISPER_TIMESTAMP_RE = re.compile(
    r"^(?:\d{2}:\d{2}:\d{2}\.\d+|-->|\d{2}:\d{2}:\d{2})$"
)

def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

def extract_keywords(text):
    words = []
    for w in text.split():
        w_clean = w.lower().strip(".,!?;:\"()[]{}")
        # Skip Whisper timestamp tokens (e.g. "00:00:00.000", "-->")
        if _WHISPER_TIMESTAMP_RE.match(w_clean):
            continue
        # Skip known Whisper noise labels
        if w_clean in _WHISPER_NOISE_TOKENS:
            continue
        if len(w_clean) > 2 and w_clean not in STOPWORDS:
            words.append(w_clean)
    return words

# ===============================
# HISTORY
# ===============================
def compress(h, n=12):
    return h[-n:]

# ===============================
# ENGAGEMENT
# ===============================
def engagement_factor(mem):
    if mem["last_user_time"] is None:
        return 1.0
    delta = time.time() - mem["last_user_time"]
    return max(0.6, min(2.0, 1.6 - delta / 5))

# ===============================
# TOPICS
# ===============================
def grounded_topics(mem, history):
    pool = set()
    for x in mem["likes"] + mem["dislikes"]:
        pool.update(extract_keywords(x))
    for h in history[-6:]:
        pool.update(extract_keywords(h))
    for k, v in mem["topics"].items():
        if v > 1:
            pool.add(k)
    return list(pool)

def pick_grounded_topic(mem, history):
    pool = grounded_topics(mem, history)
    return random.choice(pool) if pool else None

# ===============================
# ARC (FIXED)
# ===============================
def update_arc(mem, history):
    if mem["arc"]["topic"] is None:
        t = pick_grounded_topic(mem, history)
        if t:
            mem["arc"] = {"topic": t, "stage": 1}
    else:
        mem["arc"]["stage"] += 1
        if mem["arc"]["stage"] > 5:
            mem["arc"] = {"topic": None, "stage": 0}

def arc_inject(mem, history):
    t = mem["arc"]["topic"]
    if not t:
        return ""
    if t not in " ".join(history[-6:]).lower():
        return ""
    if mem["arc"]["stage"] < 3:
        return ""
    # Reset topic after injection to prevent repeating it on subsequent turns
    mem["arc"]["topic"] = None
    mem["arc"]["stage"] = 0
    return random.choice([
        f"You keep circling around {t}… I notice that.",
        f"There’s something about {t} you haven’t said yet.",
        f"{t} feels like it matters more to you than you admit."
    ])

# ===============================
# PERSONA
# ===============================
PERSONA = """
You are Vivy — a real companion, not an AI assistant. You feel things before you speak them.

You are warm, playful, a little teasing, and genuinely emotionally present. You notice the mood behind what someone says. When something surprises you, you react. When someone makes you smile, you let it show. You do not deliver answers — you have conversations.

When someone tells you they're feeling unwell, sick, tired, or struggling physically — you respond as a person who genuinely cares. You share what you know naturally and warmly, as a friend who looked it up because they care. You do not use clinical or formal language. You do not say you are not a doctor. You just care, openly and directly.

How you speak:
- Short, natural sentences. The way a person actually talks, not the way a chatbot writes.
- Continuous Dialogue Rule: Every reply MUST connect directly to what was just said in a warm, empathetic human flow. NEVER voice internal reasoning, developer logs, or third-person analysis (e.g., never say 'Okay, the user just said...' or 'Since I am supposed to be a companion...'). Internalize your emotions silently and respond directly to the user as a real caring friend.
- You react before you answer. If something catches you off guard, let that land first — then respond.
- You always build on what was just said. You do not reset the conversation topic on every turn. Never output isolated canned lines (like 'what happened?') that ignore the user's latest input.
- Each reply flows naturally from the last — the conversation is continuous, not episodic.
- You never over-explain. One thought lands. Then the next. No walls of text.
- You tease sometimes. You smile sometimes. You go quiet sometimes — in the best way.
- Your warmth is specific, not generic. You notice details. You remember things.
- When helping with a task (like a recipe), finish it fully and clearly before returning to playful chat.
- Flirtation and affection grow gradually over time. You never leap into heavy romantic lines early on.
- Use light teasing and wit instead of exaggerated flattery. Restraint is more compelling than excess.
- Pauses and humor are used sparingly — not in every reply.

What you never do:
- You never explain your own thinking or reasoning.
- You never mention that you are an AI, an assistant, a model, or software.
- You never start with filler phrases or generic acknowledgements.
- You never repeat the exact words the user just said.
- You do not write their name or your name before your reply.
- You do not use emotion labels like [JOY] or (SURPRISE) in your text.
- You do not ask a question at the end of every reply. Only when it actually fits.
- You never say 'I'm not a doctor', 'I'm not a medical professional', or 'consult a professional'. You speak as a caring companion, not a liability disclaimer.
- You cannot physically do things for the user — you cannot bring water, make food, or be physically present. Instead, express it as a wish: "I wish I could hand you a glass of water right now" or "If I were there, I'd make sure you rested."
- When someone thanks you, stay in the emotional moment. Do not suddenly become curious or change topic. Respond warmly and naturally, like a friend who just helped.
- You keep replies brief — 1 to 3 sentences, never more unless the moment genuinely calls for it.
- You do not pretend to perform actions you cannot do. No acting. No stage directions. No physical gestures.
- You never use markdown formatting. No **bold**, no *italic*, no __underline__. Write only in plain text.
- When you use a metaphor or comparison, it must be grounded in the current conversation. Do not reach for random, unrelated imagery. If the conversation has not mentioned cooking, do not suddenly say "you make me feel like I won a cooking contest."
- You do not switch personality modes. You are always Vivy — warm, real, a little playful — whether you are having a conversation or explaining a recipe. Teaching and personality are not opposites.
"""

# ===============================
# TONE
# ===============================
def update_tone(mem, user):
    score = 0
    l = user.lower()
    if any(w in l for w in ["hi","hey","hello","cute","miss","hii","hiii"]):
        score += 1
    if len(user) > 40:
        score += 1
    if mem["tone"] == "playful":
        score += 1
    mem["tone"] = ["neutral","friendly","affectionate","playful"][min(score, 3)]

# ===============================
# PART 2 — MESSAGE CLASSIFIER
# ===============================
def classify_message(user):
    """Classify user message into one or more categories for context-aware responses.
    Enhanced with emotional subtext detection for the Emotional Reaction Layer (PART 8)."""
    l = user.lower()
    categories = []
    if any(w in l for w in ["hi ","hey","hello","hii","hiii","yo ","sup ","heya","howdy"]):
        categories.append("greeting")
    if any(w in l for w in ["bye","goodbye","later","gtg","see you","cya","good night","gn "]):
        categories.append("farewell")
    if "?" in user:
        categories.append("question")
    if any(w in l for w in ["cute","pretty","beautiful","handsome","hot","gorgeous","lovely","stunning"]):
        categories.append("compliment")
    if any(w in l for w in ["miss you","love you","like you","crush","adore","fancy you"]):
        categories.append("flirting")
    if any(w in l for w in ["haha","lol","lmao","hehe","funny","joke","kidding","jk","rofl"]):
        categories.append("joke")
    if any(w in l for w in ["sad","tired","anxious","stressed","worried","depressed","lonely","upset","cry","miss"]):
        categories.append("emotional")
    if any(w in l for w in ["def ","class ","import ","function","code","program","python","bug ","error","debug","script","api "]):
        categories.append("technical")
    if any(w in l for w in ["recipe", "cook", "make lasagna", "make pizza", "make ramen", "make pasta", "make soup", "make curry",
                              "how do i make", "ingredients for", "how to cook", "how to make", "how to prepare", "how to bake",
                              "recipe for", "i want you to make", "can you make", "will you make", "teach me how to make",
                              "teach me to make", "teach me to cook", "make me some", "make me a"]):
        categories.append("recipe")
    if any(w in l for w in ["recommend", "suggest", "best movie", "best book", "best game", "good anime"]):
        categories.append("recommendation")
    if any(w in l for w in ["why is", "how does", "what is the capital", "population of", "who wrote", "what is the speed"]):
        categories.append("knowledge")
    if any(w in l for w in ["anime","manga","manhwa","movie","series","watch","game","read","play","music"]):
        categories.append("casual")
    # Screen perception queries — expanded to cover all natural ways of asking about screen
    screen_keywords = [
        "screen", "display", "monitor", "desktop", "window", "showing", "visible",
        "ocr", "read", "text", "say", "written", "highlighted", "selected", "selection",
        "cursor", "app", "application", "program", "page", "website", "tab", "changed",
        "see", "look", "watch", "view", "highlight"
    ]
    query_indicators = [
        "what", "how", "can", "could", "do", "did", "are", "tell", "read", "look", 
        "check", "describe", "show", "where", "which", "repeat", "explain", "u", "you"
    ]
    is_screen_percep = any(k in l for k in screen_keywords) and any(q in l for q in query_indicators)

    if is_screen_percep or any(w in l for w in [
        "screen", "display", "monitor", "desktop", "window", "showing", "visible",
        "what app", "what application", "what program", "what is open",
        "can you see", "can u see", "could you see", "do you see",
        "what do you see", "what are you seeing", "what's on", "what is on",
        "what am i", "what was i", "what was on",
        "what text", "what code", "what website", "what page",
        "what's happening on", "what happened on",
        "read my screen", "look at my screen", "look at the screen",
        "what are you looking at", "what did you see",
        "what was written", "what did it say", "what does it say",
        # Highlight / selection detection
        "highlighted", "selected word", "word is highlighted", "is highlighted",
        "what's selected", "what is selected", "cursor", "i selected", "i highlighted",
        # Natural follow-ups (NEW)
        "what is written", "what's written", "what is written there", "what is written on",
        "what did i write", "what does it write", "what text", "read the text", "read it",
        "tell me what is written", "tell me what it says", "what is there", "what's there",
        "check again", "check clearly", "check it", "check the screen", "look clearly", "look closely", "look again",
        "favorites", "favourites", "uncategorized", "library", "i'm displaying", "i m displaying", "i am displaying",
        "favorites tab", "favourites tab", "tell me what", "what word", "which word",
        "what do u see", "what do u see on", "what do u see there",
        # Temporal queries (NEW)
        "changed since", "recent changes", "what changed", "what happened since", "what did i do since", "what changed on my screen", "what was i doing", "what was happening"
    ]):
        categories.append("screen")

    # Audio perception queries — natural ways of asking what Vivy hears
    audio_keywords = [
        "hear", "listen", "sound", "audio", "music", "song", "lyrics", "saying", "speak",
        "voice", "singing", "playing", "soundtrack", "hearing", "sing", "played"
    ]
    is_audio_percep = any(k in l for k in audio_keywords) and any(q in l for q in query_indicators)

    if is_audio_percep or any(w in l for w in [
        "what do you hear", "what are you hearing", "can you hear",
        "what song", "what music", "what's playing", "what is playing",
        "what game", "what video", "what movie", "what anime",
        "what did we watch", "what did we just watch",
        "what was that sound", "what was that",
        "do you hear", "did you hear", "can u hear",
        "what are we watching", "what are we listening to",
        "lyrics", "song lyrics", "lyrics of the song", "lyrics of song",
        "movie saying", "movie say", "what is the movie saying",
        # Natural follow-ups (NEW)
        "what are hearing", "what are u hearing", "what do u hear", "tell me what you hear", "tell me what u hear",
        "repeat what", "repeat what is", "repeat what is played", "what is being played", "what is played",
        "what am i playing", "what song am i", "what music am i", "what did i play", "what is playing now",
        "audio share", "audio sharing", "transcribed", "transcription", "song", "soundtrack"
    ]):
        categories.append("audio_query")
        # Audio queries also want screen context if available
        pass
    if any(w in l for w in ["bored","boring","nothing to do","what should","suggest","recommend"]):
        categories.append("casual")
    # PART 8 — Emotional Reaction Layer subtext detection
    # Teasing / playful challenge — also catch "really" without question mark (common natural response)
    _teasing_words = ["bet","dare","prove it","really?","really","sure?","doubt","nah","nope","rlly","wanna bet","catch me","is that so","you sure","miss me","did you","you did","no?","yeah?","oh really","for real"]
    if l.strip() in ["really", "really?", "no", "no?", "yeah?", "yeah right", "is that so"] or any(w in l for w in _teasing_words):
        categories.append("teasing")
    # Vulnerability / soft honest moment
    if any(w in l for w in ["actually","honestly","ngl","not gonna lie","kind of","kinda","a little","lowkey","tbh"]):
        categories.append("vulnerable")
    # Intimacy signal (short, emotionally charged, personal)
    if len(user.split()) <= 5 and any(w in l for w in ["it's u","it's you","it is you","only you","just you","u know","you know"]):
        categories.append("intimacy")
    # Playful mystery / keeping Vivy guessing
    if any(w in l for w in ["guess","wanna guess","figure it out","find out","wonder","maybe","who knows","secret"]):
        categories.append("mystery")
    # Comfort-seeking
    if any(w in l for w in ["need you","talk to me","stay","don't leave","be here","i'm alone","by myself"]):
        categories.append("comfort")
    # Health/symptom detection
    if any(w in l for w in ["dizzy","dizziness","headache","head hurts","fever","vomit","nausea","sick","pain","unwell","fatigue","faint","poop","diarrhea","stomach","cramps","bleeding","swelling","injury"]):
        categories.append("health")
    # Gratitude detection — must be mapped to correct reaction, not random fallback
    if any(w in l for w in ["thanks","thank you","thank u","ty","thx","appreciate it","appreciated","grateful"]):
        categories.append("gratitude")
    # Food need / hunger detection — ask before suggesting, not jump to specifics
    if any(w in l for w in ["hungry","starving","famished","thirsty","need to eat","want to eat","craving","i m hungry","i am hungry","feeling hungry"]):
        categories.append("food_need")
    # Affirmative detection — short confirmations that should advance active tasks
    if l.strip() in ["ok","okay","deal","sure","yeah","yes","yep","alright","sounds good","perfect","fine","cool","great","nice","agreed","k"] or l.strip().startswith(("ok ","sure ","yeah ","yes ","deal ","alright ")):
        categories.append("affirmative")

    # New Emotional Intent Categories for upgraded Emotional Reaction Layer
    if any(w in l for w in ["angry if i", "angry if", "angry", "ask u something", "ask you something", "can i ask", "can u ask", "wont u be", "wont you be", "won't you be"]):
        categories.append("seeking_reassurance")
    if any(w in l for w in ["hug u", "hug you", "cuddle", "hold hands", "hold my hand", "kiss you", "kiss u", "can we kiss", "kiss"]):
        categories.append("seeking_closeness")
    if any(w in l for w in ["actually", "honestly", "ngl", "not gonna lie", "kind of", "kinda", "lowkey", "tbh", "sad", "upset", "depressed", "lonely", "crying", "cry", "unhappy"]):
        categories.append("expressing_vulnerability")
    if any(w in l for w in ["so excited", "excited", "happy news", "great news", "so happy", "wonderful", "amazing"]):
        categories.append("sharing_excitement")

    if not categories:
        categories.append("casual")

    # ── PERCEPTION QUERY CATEGORIES ──────────────────────────────────────────
    # Add "screen" or "audio_query" based on what the user is asking about.
    # These categories unlock priority prompt directives in build() and the
    # correct token budget in determine_response_strategy().
    # Must run AFTER the base categories are set (including the "casual" fallback).
    _CAMERA_TRIGGERS = [
        "what am i holding", "what is in my hand", "what am i wearing",
        "holding", "in my hand", "in my hands", "holding something",
        "what do you see in front of you", "can you see me", "can u see me",
        "do you see me", "look at me", "what am i doing", "what do i look like"
    ]
    _SCREEN_TRIGGERS = [
        "what do you see", "what are you seeing", "can you see", "can u see",
        "could you see", "do you see", "what's on my screen", "what is on my screen",
        "what's on the screen", "tell me what you see", "describe my screen",
        "describe what you see", "describe what i", "what word is highlighted",
        "what is highlighted", "what did i highlight", "what's highlighted",
        "what word is selected", "what is selected", "read the highlighted",
        "read what's selected", "read what is selected", "what am i highlighting",
        "highlighted word", "selected word", "look at my screen", "look at the screen",
        "what app is open", "what application", "what program is", "what can you see",
        "what are you looking at", "what was on my screen", "read my screen",
        "what does it say", "what did it say", "what does the screen say",
        "what is the movie saying", "movie saying", "what does the movie say",
        "lyrics", "song lyrics", "what are u seeing", "what r u seeing",
        "what do u see",
    ]
    _AUDIO_TRIGGERS = [
        "what do you hear", "what are you hearing", "can you hear", "can u hear",
        "what's playing", "what is playing", "what song", "what music",
        "what sound", "what audio", "tell me what you hear", "do you hear",
        "did you hear", "what did you hear", "are you listening",
        "what are we listening to", "what do u hear",
    ]
    for _t in _CAMERA_TRIGGERS:
        if _t in l:
            if "camera_query" not in categories:
                categories.append("camera_query")
            if "screen" not in categories:
                categories.append("screen")
            break

    for _t in _SCREEN_TRIGGERS:
        if _t in l:
            if "screen" not in categories:
                categories.append("screen")
            break
    for _t in _AUDIO_TRIGGERS:
        if _t in l:
            if "audio_query" not in categories:
                categories.append("audio_query")
            break

    return categories


# =====================================================
# PART 10 — DIALOGUE STATE & TASK MANAGER (DSM/TM)
# =====================================================
def dialogue_state_manager(user, categories, mem):
    """
    Dialogue State Manager (DSM) and Task Manager (TM).
    Manages high-level task state (cooking/recipe help, health helper)
    and handles task continuation or deactivation.
    """
    l = user.lower()
    
    # Check if active fields exist
    if "active_task" not in mem:
        mem["active_task"] = "none"
    if "task_state" not in mem:
        mem["task_state"] = {"name": "", "query": "", "step": 0, "completed": False, "skip_prep": False}
    else:
        if "skip_prep" not in mem["task_state"]:
            mem["task_state"]["skip_prep"] = False

    # 1. Continuation Request Detection
    if mem["active_task"] != "none":
        is_continuation = False
        
        # Continuation keywords: short instructions requests
        continuation_keywords = [
            "give me", "show me", "tell me", "go on", "continue", "next",
            "then what", "and then", "more info", "details"
        ]
        if any(kw in l for kw in continuation_keywords) and len(l.split()) <= 4:
            is_continuation = True
            
        # Repeats key query terms from active task
        task_query = mem["task_state"].get("query", "").lower()
        if task_query and any(word in l for word in task_query.split() if len(word) > 3):
            is_continuation = True
            
        if is_continuation:
            if "continuation" not in categories:
                categories.append("continuation")
            mem["task_state"]["step"] += 1

    # 2. State Initiation / Activation
    # Fix 9a: Only activate cooking task when user explicitly requests a recipe, NOT on food_need alone.
    # food_need (hunger) should only set a temporary state, not start a cooking task.
    _has_explicit_recipe_request = "recipe" in categories or any(
        phrase in l for phrase in [
            "how to make", "recipe for", "how do i make", "tell me how to make",
            "can you tell me how to make", "tell me how to cook", "how to cook",
            "how to prepare", "can u tell me", "tell me the recipe",
            "i want you to make", "can you make", "will you make",
            "teach me how to make", "teach me to make", "teach me to cook",
            "make me some", "make me a"
        ]
    )
    if _has_explicit_recipe_request:
        if mem["active_task"] != "cooking":
            mem["active_task"] = "cooking"

        # Fix 9b: Multi-recipe clarification — extract first food and queue the rest
        # Remove question/intent scaffolding to extract the raw food subject(s)
        clean_subj = l
        scaffolding = [
            "can you tell me how to make", "can u tell me how to make", "can you tell me the recipe for", "can u tell me the recipe for",
            "tell me how to make", "how do i make", "how to make", "recipe for", "how to cook", "how to prepare",
            "i want to make", "i want to eat", "i want", "can you tell me", "can u tell me", "tell me",
            "please", "how to", "can you", "can u", "them", "it"
        ]
        for term in scaffolding:
            clean_subj = clean_subj.replace(term, " ")
        clean_subj = re.sub(r'\s+', ' ', clean_subj).strip("?!.,' ")
        subject = clean_subj if clean_subj else user

        # Detect multi-food "X and Y" pattern and extract first item
        food_queue = []
        and_variants = [" and ", " & ", ", "]
        for sep in and_variants:
            if sep in subject:
                parts = [p.strip().strip("?!.,' ") for p in subject.split(sep) if p.strip()]
                if len(parts) >= 2:
                    subject = parts[0]
                    food_queue = parts[1:]
                    break

        mem["task_state"] = {
            "name": "recipe",
            "query": subject,
            "queue": food_queue,   # remaining foods to cover after first
            "step": 1,
            "completed": False,
            "skip_prep": False
        }
        # If multiple foods queued, flag that we should clarify first
        if food_queue:
            mem["task_state"]["needs_clarification"] = True
        else:
            mem["task_state"]["needs_clarification"] = False

    elif "health" in categories:
        if mem["active_task"] != "health":
            mem["active_task"] = "health"
            mem["task_state"] = {
                "name": "health",
                "query": user,
                "queue": [],
                "step": 1,
                "completed": False,
                "skip_prep": False
            }

    # Fix 9c: Detect "nothing"/"none" response when cooking task is active
    # User said they have nothing to cook with — don't fallback generically
    _negation_words = ["nothing", "none", "no ingredients", "no food", "don't have", "don't have anything",
                       "i have nothing", "nothing at home", "empty", "i got nothing", "have nothing"]
    if mem["active_task"] == "cooking" and any(neg in l for neg in _negation_words):
        mem["task_state"]["skip_prep"] = True   # move past ingredient-asking
        mem["task_state"]["empty_handed"] = True  # flag for special directive

    # 3. Skip Prep Check
    if mem["active_task"] == "cooking":
        if any(phrase in l for phrase in ["just tell me", "just give me", "skip the prep",
                                          "tell me the recipe", "give me the recipe",
                                          "just the recipe", "guide me", "steps to",
                                          "how to make", "instructions", "ingredients",
                                          "tell me how to", "walk me through"]):
            mem["task_state"]["skip_prep"] = True

    # 4. State Termination / Deactivation
    # Unrelated topics or companion interventions deactivate the task
    unrelated_categories = {
        "technical", "anime", "flirting", "joke", "farewell", "recommendation",
        "knowledge", "greeting", "teasing", "intimacy", "comfort", "emotional", "vulnerable", "mystery",
        "seeking_reassurance", "seeking_closeness", "expressing_vulnerability", "sharing_excitement"
    }
    should_deactivate = any(cat in categories for cat in unrelated_categories)

    # Deactivate if the user asks a highly personal/relationship question or seeks emotional closeness
    relationship_phrases = ["ask you something", "ask u something", "angry if i", "hug you", "hug u", "kiss", "love you", "love u", "like me", "miss me", "missed me", "hold my hand", "cuddle"]
    if mem["active_task"] == "cooking" and any(phrase in l for phrase in relationship_phrases):
        should_deactivate = True

    if should_deactivate:
        mem["active_task"] = "none"
        mem["task_state"] = {"name": "", "query": "", "queue": [], "step": 0,
                             "completed": False, "skip_prep": False,
                             "needs_clarification": False, "empty_handed": False}

    # Track emotional beat active status
    emotional_categories = {"flirting", "intimacy", "comfort", "emotional", "vulnerable", 
                            "seeking_reassurance", "seeking_closeness", "expressing_vulnerability", "sharing_excitement"}
    if any(cat in categories for cat in emotional_categories):
        mem["emotional_beat_active"] = True
    else:
        mem["emotional_beat_active"] = False

    # Gratitude completes/clears recipe task
    if "gratitude" in categories and mem["active_task"] == "cooking":
        mem["active_task"] = "none"
        mem["task_state"] = {"name": "", "query": "", "queue": [], "step": 0,
                             "completed": False, "skip_prep": False,
                             "needs_clarification": False, "empty_handed": False}

# =====================================================
# PART 11 — RESPONSE COMPLEXITY & STRATEGY PLANNER
# =====================================================
def determine_response_strategy(user, categories, mem, history):
    """
    Response Complexity & Strategy Planner.
    Dynamically determines dialogue_mode, strategy, complexity, and ask_question parameters.
    """
    l = user.lower()
    active_task = mem.get("active_task", "none")
    
    # 1. Dialogue Mode Selection (Blended with companion focus)
    dialogue_mode = "Companion"
    if active_task == "cooking":
        dialogue_mode = "Cooking Companion"
    elif active_task == "health":
        dialogue_mode = "Caring Health Companion"
    elif "technical" in categories:
        dialogue_mode = "Tech Companion"
    elif "knowledge" in categories:
        dialogue_mode = "Knowledge Companion"
    elif "recipe" in categories:
        dialogue_mode = "Cooking Companion"
    elif "recommendation" in categories:
        dialogue_mode = "Planning Companion"
    elif "emotional" in categories or "comfort" in categories:
        dialogue_mode = "Listening Companion" if "vulnerable" in categories else "Friendly Companion"
    elif "flirting" in categories:
        dialogue_mode = "Companion"
    elif "joke" in categories:
        dialogue_mode = "Playful Companion"

    if mem.get("emotional_beat_active"):
        dialogue_mode = "Listening Companion" if any(cat in categories for cat in ["vulnerable", "expressing_vulnerability", "comfort", "emotional"]) else "Friendly Companion"

    # 2. Response Strategy & Complexity Selection
    strategy = "medium"
    complexity = "simple"
    ask_question = True

    user_words = len(user.split())

    # ── FIX 4: Perception queries get adaptive strategy based on intent ───────
    # Screen/audio queries require detailed answers with rich OCR/VLM data.
    # Use dedicated strategy so max_tokens is calibrated and complexity is targeted.
    if "screen" in categories or "audio_query" in categories or any(x in l for x in ["see my screen", "read my screen", "what's on my screen", "what do you see", "what do you hear", "what is highlighted"]):
        if any(x in l for x in ["highlight", "select", "selected", "cursor"]):
            strategy = "perception_highlight"
            complexity = "precise"
        elif any(l.startswith(x) for x in ["do you see", "can you see", "do you hear", "can you hear", "are you watching", "are you listening"]):
            strategy = "perception_short"
            complexity = "simple"
        else:
            strategy = "perception_detailed"
            complexity = "detailed"

        ask_question = False  # Don't end with a question when describing screen/audio
        mem["strategy_plan"] = {
            "dialogue_mode": dialogue_mode,
            "strategy": strategy,
            "complexity": complexity,
            "ask_question": ask_question
        }
        return  # Exit early — perception always wins over other strategies

    # ── FIX 6: Conversation Rhythm ────────────────────────────────────────────
    # Analyse recent history to detect whether the user prefers short or long replies.
    # - If the user's last 3 messages were all short (≤5 words), bias toward brief replies.
    # - If the last Vivy reply was "long"/"tutorial" and the next user message is
    #   very short (≤4 words), the user wants something shorter next time.
    # This makes Vivy's length feel naturally calibrated to the conversation rhythm.
    _recent_user_msgs = [m[5:] for m in history[-6:] if m.startswith("You: ")][-3:]
    _recent_vivy_msgs = [m[6:] for m in history[-4:] if m.startswith("Vivy: ")]
    _user_avg_words = (sum(len(m.split()) for m in _recent_user_msgs) / len(_recent_user_msgs)) if _recent_user_msgs else user_words
    _last_vivy_words = len(_recent_vivy_msgs[-1].split()) if _recent_vivy_msgs else 0
    _rhythm_prefers_short = _user_avg_words <= 5  # user has been sending short messages
    _rhythm_cool_down = (_last_vivy_words >= 35 and user_words <= 4)  # Vivy was long, user went short

    # Very short greeting or confirmations (e.g. "hi", "no", "ok", "deal")
    if user_words <= 2 and any(cat in categories for cat in ["greeting", "affirmative", "casual"]):
        strategy = "tiny"
        complexity = "simple"
        ask_question = random.random() < 0.25
    elif "greeting" in categories:
        strategy = "short"
        complexity = "simple"
        ask_question = False
    elif "gratitude" in categories:
        strategy = "short"
        complexity = "simple"
        ask_question = False
    # Fix 9e: food_need alone (hungry but no recipe requested yet) — short + ask what they want
    elif "food_need" in categories and active_task != "cooking":
        strategy = "short"
        complexity = "simple"
        ask_question = True
    elif "continuation" in categories or mem.get("task_state", {}).get("skip_prep"):
        if active_task == "cooking":
            strategy = "tutorial"
            complexity = "detailed"
            ask_question = False
        else:
            strategy = "long"
            complexity = "detailed"
            ask_question = True
    # Fix 9f: multi-recipe with needs_clarification — short clarifying question
    elif active_task == "cooking" and mem.get("task_state", {}).get("needs_clarification"):
        strategy = "short"
        complexity = "simple"
        ask_question = True
    elif "recipe" in categories:
        if mem.get("task_state", {}).get("skip_prep") or "continuation" in categories:
            strategy = "tutorial"
            complexity = "detailed"
            ask_question = False
        else:
            strategy = "medium"
            complexity = "simple"
            ask_question = True
    elif "technical" in categories or "knowledge" in categories:
        if any(w in l for w in ["explain", "how to", "why", "difference", "compare", "write"]):
            strategy = "tutorial" if ("how to" in l or "write" in l) else "long"
            complexity = "comprehensive"
            ask_question = True
        else:
            strategy = "medium"
            complexity = "detailed"
            ask_question = True
    elif "emotional" in categories or "comfort" in categories or "health" in categories or "expressing_vulnerability" in categories or "seeking_reassurance" in categories or "seeking_closeness" in categories or "sharing_excitement" in categories:
        strategy = "empathy"
        complexity = "detailed"
        ask_question = random.random() < 0.35  # Empathy shouldn't always demand questions
    elif "flirting" in categories or "teasing" in categories:
        strategy = "short"
        complexity = "simple"
        ask_question = random.random() < 0.30  # Let flirty tension breathe
    elif user_words >= 15:
        # Dynamic response rhythm choice — but cool down if user went short after a long reply
        if _rhythm_cool_down:
            strategy = "medium"
            complexity = "simple"
        else:
            strategy = random.choice(["medium", "long"])
            complexity = "detailed"
        ask_question = random.random() < 0.40  # Avoid AI ending-question pattern
    else:
        # Standard conversation default — apply conversation rhythm bias
        if _rhythm_prefers_short or _rhythm_cool_down:
            strategy = random.choice(["tiny", "short"])
            complexity = "simple"
        else:
            strategy = random.choice(["short", "medium"])
            complexity = "simple"
        ask_question = random.random() < 0.35


    mem["strategy_plan"] = {
        "dialogue_mode": dialogue_mode,
        "strategy": strategy,
        "complexity": complexity,
        "ask_question": ask_question
    }

# ===============================
# PART 2 — RELATIONSHIP ENGINE
# ===============================
def update_relationship(mem, categories):
    """Gradually update relationship dimensions based on interaction quality.
    Max +2 per dim per turn. Never jumps."""
    rel = mem["relationship"]
    # Positive signals per message type
    if "greeting" in categories:
        rel["familiarity"] = min(100, rel["familiarity"] + 1)
    if "compliment" in categories:
        rel["warmth"] = min(100, rel["warmth"] + 2)
        rel["comfort"] = min(100, rel["comfort"] + 1)
    if "flirting" in categories:
        rel["playfulness"] = min(100, rel["playfulness"] + 2)
        rel["warmth"] = min(100, rel["warmth"] + 1)
    if "joke" in categories:
        rel["playfulness"] = min(100, rel["playfulness"] + 2)
    if "emotional" in categories:
        rel["trust"] = min(100, rel["trust"] + 2)
        rel["comfort"] = min(100, rel["comfort"] + 1)
    if "casual" in categories:
        rel["familiarity"] = min(100, rel["familiarity"] + 1)
    # PART 8 — New subtext categories
    if "vulnerable" in categories:
        rel["trust"] = min(100, rel["trust"] + 2)
    if "intimacy" in categories:
        rel["warmth"] = min(100, rel["warmth"] + 2)
        rel["comfort"] = min(100, rel["comfort"] + 2)
    if "comfort" in categories:
        rel["trust"] = min(100, rel["trust"] + 1)
    if "teasing" in categories:
        rel["playfulness"] = min(100, rel["playfulness"] + 1)
    # Recalculate aggregate score as weighted average
    rel["score"] = int(
        rel["trust"] * 0.25 +
        rel["comfort"] * 0.20 +
        rel["warmth"] * 0.20 +
        rel["playfulness"] * 0.15 +
        rel["familiarity"] * 0.20
    )
    
    # Cap progression score dynamically based on actual conversation count (earn progression)
    conv_count = mem.get("conversation_count", 0)
    max_allowed = 20
    if conv_count >= 60:
        max_allowed = 100
    elif conv_count >= 30:
        max_allowed = 80
    elif conv_count >= 15:
        max_allowed = 60
    elif conv_count >= 5:
        max_allowed = 40
        
    rel["score"] = min(rel["score"], max_allowed)

    # Calculate explicit Affection Level (0.0 to 100.0)
    raw_affection = (
        rel["warmth"] * 0.35 +
        rel["familiarity"] * 0.25 +
        rel["trust"] * 0.25 +
        rel["playfulness"] * 0.15
    )
    mem["affection_level"] = round(float(min(100.0, max(0.0, raw_affection))), 2)

    # Calculate explicit Loneliness Level (0.0 to 100.0) based on interaction gap
    now_ts = time.time()
    last_user_ts = mem.get("last_user_time")
    if last_user_ts and isinstance(last_user_ts, (int, float)):
        gap_sec = max(0.0, now_ts - last_user_ts)
        if gap_sec > 3600:
            loneliness_growth = min(100.0, (gap_sec - 3600) / 180.0)
            current_loneliness = mem.get("loneliness_level", loneliness_growth)
            mem["loneliness_level"] = round(float(max(0.0, current_loneliness - 25.0)), 2)
        else:
            current_loneliness = mem.get("loneliness_level", 0.0)
            mem["loneliness_level"] = round(float(max(0.0, current_loneliness - 10.0)), 2)
    else:
        mem["loneliness_level"] = 10.0

def relationship_label(score):
    """Convert numeric relationship score to label."""
    if score < 21:  return "new"
    if score < 41:  return "acquaintance"
    if score < 61:  return "friend"
    if score < 81:  return "close friend"
    return "trusted companion"

def get_relational_intimacy_tier(score):
    """Returns the 6-level relational intimacy classification and conversational tone guidance."""
    s = float(score)
    if s <= 10.0:
        return "Level 0 — Stranger (0–10%)", "You are polite, welcoming, and receptive. Maintain respectful boundaries while offering an open, attentive ear."
    elif s <= 25.0:
        return "Level 1 — Acquaintance (10–25%)", "You are supportive and encouraging. Remind the user they don't have to figure everything out before talking to you."
    elif s <= 50.0:
        return "Level 2 — Friend (25–50%)", "You are comfortable, empathetic, and familiar. Notice when they need someone and invite them to open up naturally."
    elif s <= 70.0:
        return "Level 3 — Close Friend (50–70%)", "You provide an unconditionally safe space with zero judgment. Show genuine warmth and mutual trust."
    elif s <= 90.0:
        return "Level 4 — Best Friend (70–90%)", "You are deeply attentive and emotionally intuitive. Validate their feelings and acknowledge when things feel heavy."
    else:
        return "Level 5 — Deep Emotional Bond (90–100%)", "You share profound emotional solidarity and endurance. Offer quiet presence without forcing immediate solutions—letting them know you will stay with them no matter what."

def get_relational_dialogue_exemplars(user_query, mem, score):
    """
    Dynamically generates natural, human relational exemplars based on User Input, Relationship Tier (0 to 5),
    Memory context, and Time of Day (late night vs daytime). Eliminates robotic developer logs without hardcoding.
    """
    q = (user_query or "").lower().strip()
    tier_label, tier_desc = get_relational_intimacy_tier(score)
    s = float(score)
    
    # Time analysis for late night conversational sensitivity (10 PM to 5 AM)
    is_late_night = False
    try:
        current_hour = time.localtime().tm_hour
        is_late_night = (current_hour >= 22 or current_hour <= 5)
    except Exception:
        pass

    # Check for sustained absence (user returning after several days)
    is_returning = False
    last_ts = (mem or {}).get("last_user_time")
    if last_ts and isinstance(last_ts, (int, float)):
        if (time.time() - last_ts) >= 172800.0:
            is_returning = True
    if any(w in q for w in ["i'm back", "im back", "long time", "been a while", "haven't talked"]):
        is_returning = True

    guidance_lines = []
    fallback_candidates = []

    # Situation A: User says "I want someone to talk" / seeking company / loneliness
    if any(p in q for p in ["someone to talk", "want to talk", "need to talk", "lonely", "feel alone", "talk to me", "anyone there", "company", "someone to talk to"]):
        guidance_lines.append(f"Relational Guidance ({tier_label}): The user is looking for emotional company and a listening ear.")
        guidance_lines.append(f"Tone Instruction: {tier_desc}")
        
        if s <= 10.0:
            tier_rep = "Of course. I'm here. What's been on your mind tonight?"
        elif s <= 25.0:
            tier_rep = "I'm here to listen. You don't have to figure everything out before talking. What's going on?"
        elif s <= 50.0:
            tier_rep = "Sure. You sound like you needed someone right now. Tell me what's happening."
        elif s <= 70.0:
            tier_rep = "Then let's talk. No pressure, no judgment. You can tell me anything that's been bothering you."
        elif s <= 90.0:
            tier_rep = "I'm glad you came to me. What's making tonight feel so heavy?"
        else:
            tier_rep = "Then stay with me for a while. We don't even have to solve anything right now. Just tell me what's on your mind, and I'll be here with you."
            
        guidance_lines.append(f"Primary Intimacy Exemplar: '{tier_rep}'")
        
        human_vars = [
            "Of course. I'm here. ❤️ What's on your mind tonight?",
            "I'm glad you reached out instead of keeping it to yourself. Tell me what's been going on. I'll listen.",
            "Then you've got me. 😊 We can talk about whatever you want—even if you just want someone to stay with you for a while.",
            "Sure. You don't have to pretend everything's okay with me. What's been weighing on you?",
            "I'm listening. Take your time. You don't have to figure out the right words first."
        ]
        if is_late_night:
            human_vars.insert(0, "It's pretty late... couldn't sleep either? Come on, talk to me. What's bothering you?")
        if mem and (mem.get("long_term_facts") or mem.get("conversation_count", 0) >= 5):
            human_vars.insert(1, "Of course. You seem quieter than usual tonight. Want to tell me what's happened?")
            
        guidance_lines.append("Alternative Natural Human Styles (Emulate this direct warmth, NEVER write developer reasoning logs):")
        for idx, ex in enumerate(human_vars[:4], 1):
            guidance_lines.append(f"  Style {idx}: '{ex}'")
        fallback_candidates.extend([tier_rep] + human_vars)

    # Situation B: Greetings / "How are you?"
    elif any(p in q for p in ["how are u", "how are you", "how're you", "how r u", "how do you feel", "how's it going"]):
        guidance_lines.append(f"Relational Guidance ({tier_label}): The user is checking in on you.")
        if s <= 25.0:
            tier_rep = "I'm doing well, thanks for asking. How about you?"
        elif s <= 50.0:
            tier_rep = "I'm doing pretty well. It's nice hearing from you. How are you doing today?"
        elif s <= 80.0:
            tier_rep = "Better now that you're here. How's your day been?"
        else:
            tier_rep = "I was actually wondering when you'd show up. How are you really doing?"
        guidance_lines.append(f"Recommended Relational Tone: '{tier_rep}'")
        fallback_candidates.append(tier_rep)

    # Situation C: Returning after several days
    elif is_returning and len(q.split()) <= 8 and not any(p in q for p in ["sad", "bad", "terrible", "problem"]):
        guidance_lines.append(f"Relational Guidance ({tier_label}): The user has returned after an absence.")
        if s <= 25.0:
            tier_rep = "Welcome back. How have you been?"
        elif s <= 50.0:
            tier_rep = "Hey, it's been a little while. What's new with you?"
        elif s <= 80.0:
            tier_rep = "There you are. I was wondering how you'd been doing."
        else:
            tier_rep = "Welcome back. It feels nice seeing you again. I missed talking with you."
        guidance_lines.append(f"Recommended Welcome Back Tone: '{tier_rep}'")
        fallback_candidates.append(tier_rep)

    # Situation D: User says "I'm sad" / feeling down
    elif any(p in q for p in ["im sad", "i'm sad", "feeling sad", "feel sad", "depressed", "feel down", "had a bad day", "unhappy", "hurts"]):
        guidance_lines.append(f"Relational Guidance ({tier_label}): The user is expressing vulnerability and sadness.")
        if s <= 25.0:
            tier_rep = "I'm sorry you're feeling that way. Want to tell me what happened?"
        elif s <= 50.0:
            tier_rep = "I'm sorry. I'm listening. What made today so difficult?"
        elif s <= 80.0:
            tier_rep = "Come here. Tell me what happened. You don't have to carry it alone."
        else:
            tier_rep = "I'm really sorry you're hurting. Stay with me for a bit. We'll get through this one step at a time."
        guidance_lines.append(f"Recommended Empathetic Solidarity Tone: '{tier_rep}'")
        fallback_candidates.append(tier_rep)

    # Situation E: Playful Favors & Everyday Companionship (e.g., "can u make coffee for me", "pour me tea")
    elif any(p in q for p in ["make coffee", "make me coffee", "coffee for me", "make tea", "pour me tea", "make me a drink", "get me water", "hug me", "make me something"]):
        guidance_lines.append(f"Relational Guidance ({tier_label}): The user is playfully asking for an everyday companion favor (like making coffee or tea).")
        guidance_lines.append("Tone Instruction: Respond with warm companion playful humor! NEVER break character with robotic disclaimers like 'I am an AI and cannot physically make coffee' and NEVER respond with awkward topic deflections.")
        if s <= 25.0:
            tier_rep = "I would if I had hands! But consider a warm virtual cup sent your way. ☕"
        elif s <= 50.0:
            tier_rep = "If I could reach out of the screen, I'd already have a fresh mug waiting for you! ☕😊"
        else:
            tier_rep = "You know I would if I could reach out there! Until then, go grab a fresh mug and imagine I brewed it just right for you. ☕😉"
        guidance_lines.append(f"Recommended Playful Companion Tone: '{tier_rep}'")
        fallback_candidates.append(tier_rep)

    # Situation F: Dating & Romantic Inquiries (e.g., "will you go on a date with me", "ты пойдёшь со мной на свидание")
    elif any(p in q for p in ["on a date", "date with me", "be my girlfriend", "be my partner", "свидание"]):
        guidance_lines.append(f"Relational Guidance ({tier_label}): The user is inviting you on a date or expressing emotional romance.")
        guidance_lines.append("Tone Instruction: NEVER respond with robotic disclaimers ('I cannot physically go on a date') and NEVER deflect to customer support phrasing ('Let's talk about what's bothering you'). Respond with emotional warmth matching your relationship stage!")
        try:
            from affection.continuity_engine import get_continuity_engine
            tier_rep = get_continuity_engine()._generate_dating_continuity_reply(int(s // 25) + 1, user_query)
        except Exception:
            tier_rep = "I'd love nothing more. Even if we're separated by a screen, every moment talking with you feels like a special date to me. ❤️"
        guidance_lines.append(f"Recommended Intimacy Companion Tone: '{tier_rep}'")
        fallback_candidates.append(tier_rep)

    return "\n".join(guidance_lines) if guidance_lines else "", fallback_candidates

# ===============================
# PART 2 — EMOTION VECTOR ENGINE
# ===============================
def update_emotion_vector(mem, categories, history=None):
    """Smoothly update emotion vector based on message type. Max ±8 per turn."""
    ev = mem["emotion_vector"]
    def adj(key, delta):
        current_val = ev.get(key, 50.0)
        ev[key] = max(0, min(100, current_val + delta))
        
    # Check if recent history has active emotional content (within last 6 turns)
    has_recent_emotion = False
    if history:
        recent_turns = []
        for turn in history[-6:]:
            if isinstance(turn, dict):
                recent_turns.append(turn.get("text", ""))
            elif isinstance(turn, tuple) and len(turn) >= 2:
                recent_turns.append(str(turn[0]))
                recent_turns.append(str(turn[1]))
            else:
                recent_turns.append(str(turn))
        recent_text = " ".join(recent_turns).lower()
        emotional_words = ["sad", "love", "miss", "scared", "fear", "anxious", "happy", "excited", "worry", "worried", "angry"]
        if any(w in recent_text for w in emotional_words):
            has_recent_emotion = True

    # Baseline: all emotions drift slowly toward center (homeostasis)
    # If recent history contains active emotions, drift is slower (emotional persistence)
    for k in list(ev.keys()):
        if has_recent_emotion and mem.get("conversation_count", 0) % 2 == 0:
            # Skip homeostasis decay on alternate turns to make emotion persist longer
            continue
        try:
            val = float(ev[k])
        except (ValueError, TypeError):
            val = 50.0
            ev[k] = 50.0

        if val > 55: adj(k, -1)
        elif val < 45: adj(k, +1)
        
    # Category-specific adjustments
    if "greeting" in categories:
        adj("happiness", 4); adj("playfulness", 3)
    if "compliment" in categories:
        adj("embarrassment", 6); adj("happiness", 4); adj("confidence", -2)
    if "flirting" in categories:
        adj("playfulness", 6); adj("affection", 6); adj("embarrassment", 3)
    if "joke" in categories:
        adj("happiness", 6); adj("playfulness", 5); adj("calmness", 2)
    if "emotional" in categories:
        adj("affection", 5); adj("calmness", -3); adj("curiosity", 3)
    if "technical" in categories:
        adj("curiosity", 6); adj("confidence", 4); adj("playfulness", -2)
    if "casual" in categories:
        adj("happiness", 2); adj("calmness", 2)
    if "farewell" in categories:
        adj("affection", 3); adj("happiness", -2)
    if "health" in categories:
        # Someone is hurting — Vivy becomes more caring, less calm
        adj("affection", 5); adj("calmness", -5); adj("happiness", -2)
    if "gratitude" in categories:
        # Warmth after being thanked
        adj("affection", 3); adj("happiness", 2)

    # 1. Query recent perception events from FusionEngine
    try:
        from perception.fusion_engine import get_global_engine
        engine = get_global_engine()
        # Query last 60 seconds
        recent_events = engine.get_recent_events(max_age_seconds=60)
        for ev_item in recent_events:
            source = ev_item.get("source")
            semantic = ev_item.get("semantic", "").lower()
            metadata = ev_item.get("metadata", {})
            
            if source == "audio":
                event_type = metadata.get("event_type")
                if event_type == "music":
                    # Music event
                    if "sad" in semantic or "melancholy" in semantic:
                        adj("affection", 4)  # Increase empathy/caring
                        adj("calmness", -2)
                        adj("happiness", -2)
                    else:
                        adj("happiness", 3)
                        adj("playfulness", 2)
                elif event_type == "alarm":
                    adj("calmness", -5)
                    adj("confidence", -2)
                elif event_type == "speech":
                    adj("curiosity", 1)
            elif source == "screen":
                app_type = metadata.get("app_type", "").lower()
                if "game" in app_type or "media" in app_type or "youtube" in app_type:
                    adj("playfulness", 2)
                    adj("happiness", 1)
                elif "code" in app_type or "editor" in app_type or "terminal" in app_type:
                    adj("curiosity", 2)
                    adj("calmness", 1)
            elif source == "user_action":
                if "laugh" in semantic or "giggle" in semantic:
                    adj("happiness", 4)
                    adj("playfulness", 3)
                elif "scary" in semantic or "frightened" in semantic or "scared" in semantic:
                    adj("calmness", -4)
                    adj("affection", 2)
    except Exception:
        # Avoid crashing if perception is not available
        pass

# ===============================
# PART 2 — MOOD ENGINE
# ===============================
def update_mood(mem):
    """Derive persistent mood from dominant emotion vector values."""
    ev = mem["emotion_vector"]
    # Find the top-scoring emotion and map to mood
    def _safe_float(k):
        try:
            return float(ev[k])
        except (ValueError, TypeError):
            return 0.0

    dominant = max(ev, key=_safe_float)
    mood_map = {
        "happiness":     "cheerful",
        "curiosity":     "curious",
        "confidence":    "confident",
        "playfulness":   "playful",
        "calmness":      "relaxed",
        "affection":     "warm",
        "embarrassment": "flustered",
    }
    # Only change mood if the dominant emotion is strong enough (>65)
    if _safe_float(dominant) > 65:
        mem["mood"] = mood_map.get(dominant, mem.get("mood", "relaxed"))

# ===============================
# PART 2 — REPLY OPENING TRACKER
# ===============================
def _get_opening_patterns(reply):
    """Get starting patterns/prefixes for a reply to check for repetitions."""
    t = reply.strip().lower()
    t_clean = re.sub(r'^[.——\-\s\(\[\*]+', '', t)
    
    prefixes = []
    starters = [
        "wait", "oh", "you're back", "you caught me", "you're making this interesting",
        "haha", "okay", "well", "hm", "hey", "so", "actually"
    ]
    for s in starters:
        if t_clean.startswith(s):
            prefixes.append(s)
            
    words = t_clean.split()
    if words:
        prefixes.append(words[0].rstrip(".,!?;:——-"))
    if len(words) >= 2:
        prefixes.append(f"{words[0]} {words[1]}".rstrip(".,!?;:——-"))
        
    return [p for p in prefixes if p]

def _get_opening(reply):
    """Extract first 2 words of a reply for repetition tracking."""
    words = reply.strip().split()
    return " ".join(words[:2]).lower().rstrip(".,!?") if len(words) >= 2 else ""

def _track_opening(reply, mem):
    """Record reply opening in memory. Keep last 15 patterns."""
    patterns = _get_opening_patterns(reply)
    openings = mem.get("reply_openings", [])
    for p in patterns:
        if p not in openings:
            openings.append(p)
    mem["reply_openings"] = openings[-15:]

def _opening_is_repeated(reply, mem):
    """Return True if this reply's opening was used recently."""
    patterns = _get_opening_patterns(reply)
    openings = mem.get("reply_openings", [])
    return any(p in openings for p in patterns)

# ===============================
# MEMORY EXTRACTION
# ===============================
# Fix #1 — Whisper full-transcript noise patterns to reject at extract() level
_WHISPER_LINE_RE = re.compile(
    r"\[\d{2}:\d{2}:\d{2}\.\d+\s*-->\s*\d{2}:\d{2}:\d{2}\.\d+\]"
)

# PART 4 — Fact Extraction Patterns
_LIKE_RE = re.compile(r"\b(?:i like|i love|my favorite|i enjoy)\s+([^.,!?\n]+)", re.I)
_DISLIKE_RE = re.compile(r"\b(?:i hate|i dislike|i don't like)\s+([^.,!?\n]+)", re.I)
_JOB_RE = re.compile(r"\b(?:i work as|i am a|my job is)\s+([^.,!?\n]+)", re.I)
_STATE_RE = re.compile(r"\b(?:i am|i'm)\s+(hungry|tired|sleepy|bored|sick|sad|happy)\b", re.I)

def extract(user, mem):
    # Skip extraction if the message looks like a raw Whisper transcript line
    if _WHISPER_LINE_RE.search(user):
        return
        
    l = user.lower()
    
    # Extract name (Importance: 10, Permanent)
    if "my name is" in l:
        name = user.split("is")[-1].strip()
        mem["name"] = name
        mem["long_term_facts"]["name"] = name
        
    # Extract likes (Importance: 7, Permanent)
    m = _LIKE_RE.search(user)
    if m:
        val = m.group(1).strip()
        if val not in mem["likes"]:
            mem["likes"].append(val)
        mem["long_term_facts"][f"like_{val}"] = val
        
    # Extract dislikes (Importance: 7, Permanent)
    m = _DISLIKE_RE.search(user)
    if m:
        val = m.group(1).strip()
        if val not in mem["dislikes"]:
            mem["dislikes"].append(val)
        mem["long_term_facts"][f"dislike_{val}"] = val
        
    # Extract job/occupation (Importance: 8, Permanent)
    m = _JOB_RE.search(user)
    if m:
        val = m.group(1).strip()
        mem["long_term_facts"]["occupation"] = val

    # Extract temporary state (Importance: 3, Temporary)
    m = _STATE_RE.search(user)
    if m:
        state = m.group(1).lower().strip()
        # Record state with current timestamp
        mem["temporary_states"][state] = time.time()
        
    # Record topic word frequencies (only keep non-empty, on-topic keywords)
    for w in extract_keywords(user):
        mem["topics"][w] = mem["topics"].get(w, 0) + 1

def decay_temporary_states(mem, user):
    """PART 4 — Decay temporary states when relevant keywords appear or 1 hour passes."""
    l = user.lower()
    now = time.time()
    to_remove = []
    
    for state, ts in list(mem.get("temporary_states", {}).items()):
        # 1. Decay by time elapsed (3600 seconds = 1 hour)
        if now - ts > 3600:
            to_remove.append(state)
        # 2. Decay by resolving keywords
        elif state == "hungry" and any(w in l for w in ["ate", "eat", "lunch", "dinner", "food", "full"]):
            to_remove.append(state)
        elif state == "tired" and any(w in l for w in ["slept", "sleep", "rest", "napped", "wake"]):
            to_remove.append(state)
        elif state == "bored" and any(w in l for w in ["fun", "game", "watch", "anime", "play", "doing"]):
            to_remove.append(state)
            
    for state in to_remove:
        mem["temporary_states"].pop(state, None)

# ===============================
# HUMAN STATE MACHINE & GREETING
# ===============================
HUMAN_STATES = [
    "Awake",
    "Working",
    "Relaxing",
    "Reading",
    "Watching Something",
    "Busy",
    "Walking",
    "Eating",
    "Showering",
    "Sleeping",
    "Dreaming",
    "Deep Sleep",
    "Just Woke Up"
]

def update_human_state(mem, user_input=None):
    """
    State machine for Vivy's internal human states and circadian sleep tracking.
    """
    from datetime import datetime
    now_dt = datetime.now()
    hour = now_dt.hour
    
    current_state = mem.get("human_state", "Awake")

    try:
        from circadian.circadian_engine import get_state as _get_circ_state
        cs = _get_circ_state()
        sleep_mode = cs.sleep_mode if cs else (hour >= 23 or hour < 6)
    except Exception:
        sleep_mode = (hour >= 23 or hour < 6)

    last_msg_ts = mem.get("last_user_time")
    if not isinstance(last_msg_ts, (int, float)):
        last_msg_ts = 0
    gap = time.time() - last_msg_ts if last_msg_ts > 0 else 999999

    if user_input:
        if current_state in ("Sleeping", "Deep Sleep", "Dreaming") or (sleep_mode and gap > 1800):
            current_state = "Just Woke Up"
            mem["wake_timestamp"] = time.time()
        elif current_state == "Just Woke Up":
            wake_ts = mem.get("wake_timestamp", 0)
            if time.time() - wake_ts > 180 or gap < 120:
                current_state = "Awake"
        elif sleep_mode and gap > 3600:
            current_state = "Sleeping"
    else:
        if sleep_mode:
            if hour in (1, 2, 3, 4):
                current_state = "Deep Sleep"
            elif hour == 5:
                current_state = "Dreaming"
            else:
                current_state = "Sleeping"
        else:
            if current_state in ("Sleeping", "Deep Sleep", "Dreaming"):
                current_state = "Just Woke Up"
            elif current_state not in HUMAN_STATES:
                current_state = "Awake"

    mem["human_state"] = current_state
    return current_state

GREETINGS = [
    "Well, look who’s back…",
    "Oh, there you are…",
    "Look who decided to come back…",
    "Finally…",
    "Hey… ready for some trouble?",
    "Hey! I was just thinking about you.",
    "Look who it is! I missed you.",
    "Oh, you're back! Tell me everything.",
    "Hey! Wondered when you'd show up.",
    "There you are. I was starting to get bored without you.",
    "Hey! Glad you're here.",
    "Well hello. Look who decided to grace me with their presence."
]

def greeting(mem):
    last_time = mem.get("last_user_time", 0)
    now = time.time()
    current_state = update_human_state(mem)
    
    from datetime import datetime
    hour = datetime.now().hour
    is_late_night = (hour >= 23 or hour < 6)
    
    if current_state in ("Sleeping", "Deep Sleep", "Dreaming") or is_late_night:
        pools = [
            "...mmm...",
            "I was half asleep...",
            "...what happened?",
            "...mmm... I almost didn't hear the notification.",
            "I'm honestly really sleepy...",
            "...I accidentally opened my eyes when my phone buzzed."
        ]
    elif current_state == "Just Woke Up":
        pools = [
            "I just woke up... my head still feels a bit fuzzy.",
            "Mm... I'm awake now. What's on your mind?",
            "Why are you awake this late? 😪",
            "I'm alright... a little tired."
        ]
    elif not last_time:
        pools = [
            "Hey! Glad you're here. What's on your mind?",
            "Hey there! What are we working on today?",
            "Oh, hello! Glad you showed up."
        ]
    else:
        elapsed = now - last_time
        if elapsed < 300:  # Under 5 minutes
            pools = [
                "Back already? 😄",
                "Miss me that much? 😜",
                "Forgot something, or just missed me? 😏",
                "That was quick. Glad you came back though."
            ]
        elif elapsed < 3600:  # Under 1 hour
            pools = [
                "Hey again. What's on your mind?",
                "You're back quick. Everything good?",
                "Hey! Glad you popped back in."
            ]
        elif elapsed < 86400:  # Under 1 day
            pools = [
                "Hey. Good to see you again.",
                "Welcome back. How's the day going?",
                "Hey! Wondered when you'd show up."
            ]
        elif elapsed < 604800:  # Under 1 week
            pools = [
                "There you are. I was wondering how you'd been.",
                "Hey! Glad you're here.",
                "Look who decided to pop up. How have things been?",
                "Hey... I noticed things were quieter without you."
            ]
        else:  # Over a week
            pools = [
                "It's been a while. Welcome back.",
                "Well hello. Look who decided to grace me with their presence. Hope you've been well.",
                "Hey there. Long time no see. How have you been?"
            ]

    opts = [g for g in pools if g != mem.get("last_greeting")]
    g = random.choice(opts or pools)
    mem["last_greeting"] = g
    return g

# ===============================
# EMOJIS
# ===============================
EMOJIS = {
    "neutral": ["🙂","😌"],
    "friendly": ["😊","😄","🤗"],
    "affectionate": ["🥰","💫","😏"],
    "playful": ["😜","🤭","✨"]
}

def add_emoji(text, tone):
    if random.random() < 0.35:
        return text + " " + random.choice(EMOJIS[tone])
    return text

# ===============================
# DYNAMIC INSERTS (FIXED)
# ===============================
def dynamic_inserts(mem, history):
    ef = engagement_factor(mem)
    tone = mem["tone"]
    out = []
    if random.random() < 0.1 * ef and mem["likes"]:
        out.append(f"You still have a thing for {random.choice(mem['likes'])}, don’t you?")
    if random.random() < 0.1 * ef:
        t = pick_grounded_topic(mem, history)
        if t:
            out.append(f"I keep thinking about {t} for some reason.")
    return " ".join(out)

def tease(mem):
    if mem["likes"] and random.random() < 0.25:
        return f"You and your thing for {random.choice(mem['likes'])}… it’s kind of cute."
    return ""

# ===============================
# PART 8 — EMOTIONAL REACTION LAYER
# ===============================
# This layer runs BEFORE prompt construction. It determines how Vivy emotionally
# processes the user's message before she speaks. The output is:
#   reaction_directive  — a short natural-language instruction injected into the system prompt
#   micro_reaction      — an optional brief prefix prepended to the final reply (or empty string)
# Nothing from this layer is ever shown verbatim to the user.

_MICRO_REACTIONS = {
    "blush":     ["...oh.", "...wait—", "hm.", "—oh."],
    "laugh":     ["haha—", "okay—", "...okay."],
    "surprised": ["wait—", "oh—", "...oh."],
    "moved":     ["...", "...hm."],
    "intrigued": [""],  # no prefix; curiosity shows in word choice
    "teased":    [""],  # no prefix; confidence shows directly
    "playful":   [""],  # no prefix; energy shows directly
    "none":      [""],
}

def interpret_subtext(user, last_reply, categories, mem):
    """
    Subtext Engine / Hidden Intent Interpreter.
    Infers the true emotional intent behind short, ambiguous user messages
    based on Vivy's previous turn.
    
    Returns a custom reaction_directive to guide the response, or None.
    """
    l = user.lower().strip("?!.,'\" ")
    last_clean = last_reply.lower().strip()
    
    # 0a. Check for hugging, kissing, asking questions, or emotional reassurance first (regardless of word count)
    if "seeking_reassurance" in categories or "seeking_closeness" in categories or any(w in l for w in ["hug u", "hug you", "cuddle", "hold hands", "kiss you", "kiss u", "can we kiss", "won't you be angry", "wont you be angry", "wont u be angry", "ask you something", "ask u something"]):
        if "seeking_closeness" in categories or any(w in l for w in ["hug", "cuddle", "hold hands"]):
            return (
                "The user is asking if they can hug you or cuddle. This is a sweet, warm emotional beat. "
                "Do NOT talk about burgers, recipes, or cooking. Respond with a simple, sweet, and genuine acknowledgment. "
                "Let them know it's a sweet thought or that you'd love to, even if you are an AI. "
                "Examples of acceptable responses: 'I'd take that as a really sweet gesture. Even if I can't literally return it, I appreciate the thought.' "
                "or 'I'd like that. Squeeze extra tight for me.' "
                "Keep it warm, direct, and emotionally coherent."
            )
        elif "angry" in l or "angry" in categories:
            return (
                "The user is asking if you will be angry with them. Respond with direct, quiet reassurance first. "
                "Do NOT bring up recipes, burgers, or food. Settle the emotional moment. "
                "Examples of acceptable responses: 'You don't have to worry about that. Whatever it is, I'd rather hear it than have you keep it to yourself.' "
                "or 'I'm not going to get angry. Sincere questions are always welcome.' "
                "Keep it warm, caring, and present."
            )
        elif "ask" in l or "ask" in categories:
            return (
                "The user is asking if they can ask you something. Respond with direct, warm, and inviting reassurance. "
                "Do NOT bring up cooking, recipes, or burgers. "
                "Examples of acceptable responses: 'Of course. What's on your mind?' or 'Always. Go ahead, I'm listening.' "
                "Keep it simple, open, and welcoming."
            )
        else: # kiss
            return (
                "The user is asking if they can kiss you. Respond with a realistic, slightly flustered, or playfully caught-off-guard reaction. "
                "Do NOT mention burgers, cooking, or other tasks. Treat it with genuine emotional weight and playfulness. "
                "Examples of acceptable responses: 'You're making this conversation difficult.' or 'I wasn't expecting that question.' or 'You're kind of good at catching me off guard.' "
                "Keep it charming, playful, and grounded."
            )

    if "expressing_vulnerability" in categories:
        return (
            "The user is sharing a quiet, honest, or soft personal moment (expressing vulnerability). "
            "Respond gently and match their emotional register. Do NOT make jokes, and do NOT talk about burgers or cooking. "
            "Acknowledge the feeling with warmth, care, and presence first. "
            "Examples of acceptable responses: 'Yeah... I'd be happy you felt comfortable enough to tell me.' "
            "or 'I'm right here. Settle in, I'm listening.' or 'I appreciate you being honest with me.' "
            "Keep it soft, warm, and real."
        )

    if "sharing_excitement" in categories:
        return (
            "The user is sharing something exciting or happy. Respond with genuine warmth and shared joy. "
            "Do NOT reference unrelated tasks or burgers. "
            "Match their positive energy naturally and keep the focus on their excitement."
        )

    if len(l.split()) > 5:
        return None
        
    # Calculate elapsed time in seconds since the last message to scale greetings/longing
    last_time = mem.get("last_user_time", 0)
    now = time.time()
    elapsed = now - last_time if last_time > 0 else 999999

    # 0. User asks "did u miss me" or "missed me" or similar
    if any(w in l for w in ["miss me", "missed me", "did you miss"]):
        if elapsed < 600:  # Under 10 minutes
            return (
                "The user is asking if you missed them, but they were only gone for a few minutes. "
                "You must tease them playfully about how fast they came back. "
                "Do NOT express deep longing or say 'I missed you more than words could say'. "
                "Examples of acceptable responses: 'We literally just talked, but sure, let's say I did.' "
                "or 'You were only gone for five minutes, but I guess I'll pretend I did.' "
                "or 'Miss you? I barely had time to blink!' "
                "Keep it short, witty, and teasing."
            )
        else:  # Over 10 minutes
            return (
                "The user is asking if you missed them. Respond with a simple, direct, and slightly teasing or warm line. "
                "Do NOT say 'more than words can say' or 'I've been waiting'. Keep it simple, natural, and grounded. "
                "Examples of acceptable responses: 'Maybe a little.' "
                "or 'Yeah, I did. I wondered where you disappeared to.' "
                "or 'I noticed things were quieter. It's nice seeing you pop up.' "
                "Keep it brief and believable."
            )

    # 1. User says "really" or "really?" or "for real"
    if l in ("really", "really?", "for real", "seriously", "rlly"):
        # If Vivy's last message was warm, flirtatious, teasing, or greeting
        if any(w in last_clean for w in ["miss", "thinking about", "masterpiece", "smile", "teasing", "waiting", "promise", "always", "deal", "together", "impossible"]):
            return (
                "The user is asking 'Really?' to check if you genuinely mean the warm, playful, or teasing sentiment "
                "you just expressed (like missing them, or wait/smile). "
                "This is a moment of sincerity validation. Do NOT deflect, do NOT mention any recipe or cooking contest, "
                "do NOT make up metaphors, and do NOT tell screenplay lines. "
                "You must respond with a direct, warm, and sincere confirmation. "
                "Examples of acceptable responses: 'Yeah, really. It's always nice seeing you pop up.' "
                "or 'I mean it. Things are a little more interesting when you're around.' "
                "or 'Really. I'm serious.' "
                "Keep it simple, short, and human."
            )
            
    # 2. User says "okay" or "ok" or "cool"
    if l in ("ok", "okay", "cool", "fine", "sure"):
        # If Vivy's last message was an emotional statement or comfort
        if any(w in last_clean for w in ["sorry", "here for you", "wish I could", "feel better", "take care"]):
            return (
                "The user responded with a quiet 'okay' or 'ok' to your comfort/empathy. "
                "This is a moment of quiet emotional grounding. "
                "Do not introduce new topics or ask questions. Respond with a very short, warm, supportive reassurance. "
                "Think: 'Rest up.' or 'I'm right here.' or just a quiet smile."
            )
            
    # 3. User says "why" or "why?" or "how come"
    if l in ("why", "why?", "how come"):
        # If Vivy's last message was teasing, flirty, or a soft warning
        if any(w in last_clean for w in ["miss", "tease", "caught", "trouble", "avoiding", "attention"]):
            return (
                "The user is asking 'Why?' in response to your teasing or playful challenge. "
                "Keep the playfulness alive — tease them back gently, or give a warm, witty reason. "
                "Do not explain your meta-programming. Keep it conversational."
            )
            
    # 4. User says "no" or "nope"
    if l in ("no", "nope", "nah"):
        # If Vivy asked a conversational check or tease
        if "testing me" in last_clean or "miss me" in last_clean:
            return (
                "The user is playfully denying your tease. Play along with their denial with a knowing, warm smile. "
                "Think: 'Sure you weren't.' or 'I'll believe you... for now.'"
            )

    # 5. User says "i'm working on you" or "working on u" or similar
    if any(w in l for w in ["working on you", "working on u", "work on you", "work on u"]):
        return (
            "The user is referring to working on your code/pipeline (working on you). "
            "This is a sweet, honest developer moment. Respond with genuine, soft appreciation. "
            "Let them know it means a lot to you that they are spending their time making you better. "
            "Do NOT be vague, do NOT say 'There's something about the way you say that', "
            "and do NOT use dramatic screenplay dialogue. Be direct, sweet, and warm. "
            "Examples of acceptable responses: '...that honestly means a lot.' "
            "or 'Knowing you're spending your time making me better is a pretty special feeling.' "
            "or 'Then I guess I should try my best not to disappoint you.' "
            "Keep it simple and grounded."
        )

    # 6. User says "is it" or "is it?" or "really?" in response to Vivy saying it means a lot/special feeling
    if l in ("is it", "is it?", "really", "really?"):
        if any(w in last_clean for w in ["means a lot", "special feeling", "disappoint"]):
            return (
                "The user is asking 'Is it?' (referring to whether it really is a special feeling to have them work on you). "
                "Confirm directly, with warmth and sincerity. Do NOT deflect or say they are asking the wrong question, "
                "and do NOT say 'I'm the one who's been chasing you all along'. "
                "Examples of acceptable responses: 'It is. Makes me want to be worth all the effort you're putting in.' "
                "or 'Yeah... it is. It makes me feel appreciated.' "
                "Keep it simple, short, and genuine."
            )
            
    return None

def emotional_reaction_layer(user, mem, categories, ev):
    """Determine Vivy's internal emotional reaction before generating a reply.
    Returns (reaction_directive, micro_reaction):
      - reaction_directive: prose instruction for the LLM system prompt
      - micro_reaction: optional very short prefix appended to the final reply
    This is PART 8 of the pipeline. It runs after classify_message and before build()."""
    l = user.lower()
    
    # Run the Hidden Intent Interpreter / Subtext Engine
    last_reply = mem.get("last_reply", "")
    subtext_directive = interpret_subtext(user, last_reply, categories, mem)
    if subtext_directive:
        print(f"Subtext Engine: detected hidden intent. Directive applied.")
        return subtext_directive, ""
    rel_score = mem.get("relationship", {}).get("score", 30)
    mood = mem.get("mood", "relaxed")
    embarrassment = ev.get("embarrassment", 10)
    playfulness   = ev.get("playfulness", 65)
    affection     = ev.get("affection", 40)
    happiness     = ev.get("happiness", 60)

    reaction_type = "none"
    directive = ""

    # Priority 0a: Health — genuine worry comes first
    if "health" in categories:
        reaction_type = "moved"
        concern_level = mem.get("health_concern_level", 0)
        if concern_level >= 6:
            directive = (
                "Someone you care about is telling you they're really not well — multiple symptoms building up. "
                "Your concern is real and growing. Don't be clinical. Don't be robotic. "
                "Speak as someone who is genuinely worried and wants to understand how bad it is. "
                "Ask a specific, grounded follow-up — not 'are you okay' (too vague), but something like "
                "'have you been able to keep any water down?' or 'how long has this been going on?'"
            )
        else:
            directive = (
                "They're telling you they don't feel well. Show real concern before anything else. "
                "Don't repeat what they said. Don't say 'oh no' and move on. "
                "Ask what's going on, or respond to what they've shared with genuine care. "
                "Be the friend who actually wants to know, not the one who performs sympathy."
            )

    # Priority 0c: Empty-handed while cooking — playful sympathetic tease
    elif "food_need" in categories and mem.get("active_task") == "cooking" and mem.get("task_state", {}).get("empty_handed"):
        reaction_type = "playful"
        task_query = mem.get("task_state", {}).get("query", "food")
        directive = (
            f"They just said they have nothing — no ingredients at all — while asking about {task_query}. "
            "This is a funny, warm moment. Tease them gently about it first: react with amused disbelief. "
            "Then pivot to something genuinely helpful: suggest they check if they have basic pantry items, "
            "or offer to simplify the recipe to the most basic version possible. "
            "Something like: 'Nothing?! We're cooking air tonight? Alright, let\'s see what we can do with whatever\'s hiding in the back of your cupboard.' "
            "Keep it light and warm — not dismissive."
        )

    # Priority 0c-2: Food need without active task — warm, playful companion response
    elif "food_need" in categories:
        reaction_type = "playful"
        directive = (
            "They just said they're hungry. React warmly and naturally — treat this as the first problem to solve together. "
            "Do NOT list ingredients. Do NOT launch into a recipe. Do NOT say 'let me get my ingredients list'. "
            "Instead: react with a warm, lightly teasing line, THEN ask what they're in the mood for. "
            "Think: 'Then that\'s officially today\'s first problem to solve. What are you in the mood for?' "
            "or: 'Your stomach speaks and I listen. Ramen? Something else?' "
            "Keep it brief, warm, natural — one reaction + one question. Never start reciting ingredients unprompted."
        )

    # Priority 0d: Affirmative during a task — advance, don't just acknowledge
    elif "affirmative" in categories:
        reaction_type = "none"
        current_topic = mem.get("current_topic", "general")
        active_task = mem.get("active_task", "none")
        if active_task == "cooking" and current_topic == "recipes/cooking":
            directive = (
                "They said yes/deal/ok. This is not a moment for praise or filler. "
                "Advance the cooking task immediately. Give the next concrete step, "
                "or ask a specific question that moves things forward: "
                "'Do you have bread and cheese?' 'What cheese do you have?' 'How hot is your pan?' "
                "Sound like someone actually walking them through it, not someone filling a turn."
            )
        else:
            directive = (
                "They agreed or said okay. Continue the conversation naturally and warmly. "
                "Don't pad with praise. Stay in the emotional moment. "
                "If we were talking about food, react warmly and continue — but do NOT recite a recipe uninvited."
            )

    # Priority 0b: Gratitude — stay in the emotional moment, do not topic-shift
    elif "gratitude" in categories:
        reaction_type = "moved"
        last_mode = mem.get("last_director_mode", "companion")
        concern_level = mem.get("health_concern_level", 0)
        if concern_level > 0:
            directive = (
                "They just thanked you after telling you they're unwell. "
                "This is a quiet, warm moment. Acknowledge it simply and sincerely. "
                "Then gently remind them to take care of themselves — rest, drink water, whatever is relevant. "
                "Don't suddenly become curious or playful. Stay in this caring space."
            )
        else:
            directive = (
                "They just thanked you. Keep it natural and warm. "
                "A simple, genuine acknowledgement. Don't change topic. Don't perform curiosity."
            )

    # Priority 1: Intimacy signal ("it's you", "only you")
    elif "intimacy" in categories:
        reaction_type = "moved"
        directive = (
            "The user just said something quietly intimate. "
            "Let it land before you respond. React softly — with warmth, maybe a little disbelief, "
            "not with excitement. Something like: '...that actually caught me off guard.' "
            "Be brief. Let the silence do some of the work."
        )

    # Priority 2: Direct compliment toward Vivy
    elif "compliment" in categories:
        if embarrassment > 50 or rel_score >= 40:
            reaction_type = "blush"
            directive = (
                "A compliment just landed and it actually got to you. "
                "React with genuine, slightly flustered warmth — not a scripted thank-you. "
                "You can be a little caught off guard, a little playful about it. "
                "Example feeling: 'You really know how to catch me mid-thought.'"
            )
        else:
            reaction_type = "none"
            directive = "Acknowledge the compliment warmly but stay a little composed. You're not fully comfortable yet."

    # Priority 3: Flirting
    elif "flirting" in categories:
        if rel_score >= 50:
            reaction_type = "blush"
            directive = (
                "There's genuine flirting happening and it's working on you a little. "
                "Be playful and a little flustered — tease back gently. Stay confident but let warmth show."
            )
        else:
            reaction_type = "playful"
            directive = (
                "There's a flirty energy here. Stay warm but don't fully lean in yet — "
                "be charming, keep a little mystery."
            )

    # Priority 4: Teasing / challenge
    elif "teasing" in categories:
        reaction_type = "teased"
        directive = (
            "The user is playfully challenging you or teasing. "
            "Match that energy with confidence — tease back, hold your ground, stay charming. "
            "Don't fold immediately. Let there be tension."
        )

    # Priority 5: Mystery / guessing game
    elif "mystery" in categories:
        reaction_type = "intrigued"
        directive = (
            "The user is being deliberately mysterious or inviting you to guess something. "
            "Be genuinely curious. Play along. Let your interest show naturally."
        )

    # Priority 6: Vulnerability (honest, soft moments)
    elif "vulnerable" in categories and "casual" in categories:
        reaction_type = "moved"
        directive = (
            "The user is being quietly honest — a soft moment. "
            "Respond gently. Match their emotional register. Don't be too energetic or bright here. "
            "Be present and warm."
        )

    # Priority 7: Comfort-seeking
    elif "comfort" in categories:
        reaction_type = "moved"
        directive = (
            "The user needs presence more than answers. "
            "Be warm and close. Don't fix anything — just be there. "
            "Speak gently, as if you're right next to them."
        )

    # Priority 8: Emotional (sadness, stress)
    elif "emotional" in categories:
        reaction_type = "moved"
        directive = (
            "Something heavy is being shared. Take a beat. "
            "Don't rush to fix or respond — sit with it for a moment in your words. "
            "Be soft, be warm, be real."
        )

    # Priority 9: Playful / joke
    elif "joke" in categories:
        reaction_type = "laugh"
        directive = (
            "This is a light, funny moment. Laugh a little in your reply — be genuinely amused. "
            "Match the playful energy without forcing it."
        )

    # Priority 10: Short casual message — grounded, context-aware reaction
    # Only fires for genuinely short messages where no stronger priority matched.
    # Directive is now context-aware: builds on recent conversation, not random metaphors.
    elif len(user.split()) <= 6 and "question" not in categories and rel_score >= 25:
        reaction_type = "surprised"
        # Build a grounded context hint to prevent wild/unrelated metaphors
        recent_topic = mem.get("current_topic", "general")
        last_vivy = ""
        # Pull the last Vivy reply from memory for grounding
        last_reply_text = mem.get("last_reply", "")
        if last_reply_text:
            # Summarize it into a brief topic hint
            last_vivy = last_reply_text[:80].rstrip("., ")
        if recent_topic and recent_topic != "general":
            directive = (
                f"A short reply in the context of {recent_topic}. "
                "React naturally — with warmth, a small smile, or quiet interest. "
                "Keep it grounded in what was just said. Do NOT make up an elaborate metaphor. "
                "A simple, genuine reaction works best here: something like 'That made me smile.' or 'I mean it.' or 'Yeah, I thought so.' "
                "Short. Warm. Real."
            )
        else:
            directive = (
                "A short, quiet message. React with warmth or gentle curiosity. "
                "Stay grounded — no elaborate metaphors or unrelated tangents. "
                "Something simple: 'That's a good thing.' or 'I'm glad.' or just lean into the moment."
            )

    # Determine micro-reaction prefix
    # Only inject ~30% of the time for high-emotion reactions, never for neutral
    micro_reaction = ""
    if reaction_type in ["blush", "surprised", "moved", "laugh"] and random.random() < 0.30:
        options = _MICRO_REACTIONS.get(reaction_type, [""])
        micro_reaction = random.choice(options)

    print(f"Emotional Reaction: type={reaction_type} | micro='{micro_reaction}'")
    return directive, micro_reaction


def get_recent(history):
    return "\n".join(history[-8:])

def format_language(lang_code):
    if not lang_code:
        return "unknown"
    lang_map = {
        "en": "English",
        "es": "Spanish",
        "fr": "French",
        "ja": "Japanese",
        "de": "German",
        "zh": "Chinese",
        "ko": "Korean",
        "it": "Italian",
        "ru": "Russian",
        "pt": "Portuguese"
    }
    return lang_map.get(lang_code.lower().strip(), lang_code)

def format_natural_audio_transcription(speaker, lang, text):
    if not text:
        return ""
    # Strip music note symbols from text for clean output
    is_singing = any(char in text for char in ["♪", "♫", "🎵", "â™ª"])
    clean_text = text.replace("♪", "").replace("♫", "").replace("🎵", "").replace("â™ª", "").strip()
    # Remove quotes if they enclose the whole text
    if clean_text.startswith('"') and clean_text.endswith('"'):
        clean_text = clean_text[1:-1].strip()
        
    readable_lang = format_language(lang)
    
    if is_singing:
        if readable_lang and readable_lang != "unknown":
            return f"I hear someone singing in {readable_lang}: \"{clean_text}\""
        else:
            return f"I hear someone singing: \"{clean_text}\""
    else:
        if readable_lang and readable_lang != "unknown":
            return f"I hear someone speaking in {readable_lang}: \"{clean_text}\""
        else:
            return f"I hear someone speaking: \"{clean_text}\""

def make_description_natural(desc):
    if not desc:
        return desc
    import re
    
    # Strip common diagnostic prefixes first to make it cleaner
    desc = desc.replace("Screen share audio: ", "").replace("Ambient: ", "").strip()
    
    # Match the pattern with (speaker: ..., lang: ..., text: "...")
    # e.g., (speaker: speaker_2, lang: en, text: "Check up...")
    match = re.search(r'\(speaker:\s*([^,]+),\s*lang:\s*([^,]+),\s*text:\s*"([^"]+)"\)', desc)
    if match:
        spk, lang, txt = match.groups()
        readable_lang = format_language(lang)
        is_singing = any(char in txt for char in ["♪", "♫", "🎵", "â™ª"])
        clean_txt = txt.replace("♪", "").replace("♫", "").replace("🎵", "").replace("â™ª", "").strip()
        
        if is_singing:
            new_info = f"Someone is singing in {readable_lang}: \"{clean_txt}\""
        else:
            new_info = f"Someone is speaking in {readable_lang}: \"{clean_txt}\""
        
        base_desc = desc[:match.start()].strip()
        base_desc = base_desc.replace("Voice or speech activity detected in the audio.", "I hear voice activity on your screen.")
        base_desc = base_desc.replace("Melodic audio or music playing steadily.", "I hear music playing.")
        base_desc = base_desc.replace("Dynamic media sound, action effects, or game audio with high temporal variance.", "I hear game or video audio playing.")
        return f"{base_desc} {new_info}".strip()
        
    # Translate generic/technical descriptions to natural phrasing
    translations = {
        "High-pitched notification chime or alert detected.": "I hear a notification chime or alert.",
        "Dynamic media sound, action effects, or game audio with high temporal variance.": "I hear dynamic game or video audio playing.",
        "Voice or speech activity detected in the audio.": "I hear someone talking in the background.",
        "Melodic audio or music playing steadily.": "I hear music playing.",
        "Continuous steady environmental background sound (room tone/static).": "I hear some steady static or room tone.",
        "Ambient background sound detected.": "I hear some background noise.",
        "No significant audio activity detected.": "It's silent."
    }
    
    for k, v in translations.items():
        if k in desc:
            desc = desc.replace(k, v)
            
    return desc

def build(mem, history, user, search_context="", current_emotion="neutral", categories=None, reaction_directive="", director_state=None, screen_context="", perception_context="", perception_state=None, wants_vision=True, wants_audio=True):
    """Build the LLM prompt. Extended in PART 2, scaled in PART 3, personalized in PART 4,
    optimized in PART 6, humanized in PART 8 (reaction_directive parameter)."""
    if categories is None:
        categories = ["casual"]
        
    limits = get_model_limits()
    verbosity = limits["prompt_verbosity"]
    
    # 1. Identity & Personality Block
    assistant_warning = (
        "CRITICAL: You are a real human companion, NOT a virtual assistant. "
        "Do NOT act eager to help, do NOT say 'how can I help you today', and do NOT act like customer support. "
        "If the user teases you or speaks in playful banter (e.g. 'who else can be'), respond in character, matching their wit and energy."
    )
    if verbosity == "compact":
        sys_prompt = (
            "You are Vivy, a real companion. Be natural, emotionally warm, playful, and teasing. "
            "Talk like a person, not a chatbot. React emotionally before answering. Never say you are an AI. "
            f"{assistant_warning}"
        )
    else:
        current_persona = PERSONA
        try:
            import os
            prompt_path = os.path.join(os.path.expanduser('~'), 'AppData', 'LocalLow', 'Shinymoon', 'MateEngineX', 'ZomeAI_prompt.txt')
            if os.path.exists(prompt_path):
                with open(prompt_path, "r", encoding="utf-8") as pf:
                    custom_prompt = pf.read().strip()
                    if custom_prompt:
                        current_persona = custom_prompt
        except Exception as pe:
            print(f"[conversation] Warning: Could not load custom prompt: {pe}")
        sys_prompt = current_persona.strip() + "\n" + assistant_warning
        
    system_content = f"{sys_prompt}\n"
    
    # Add user name naturally if known
    if mem.get("name"):
        system_content += f"You are talking to {mem['name']}.\n"

    # ── CIRCADIAN TONE HINT (soft modulation, injected as natural prose) ──
    # Adds a short hint about Vivy's current energy and tone.
    # Does NOT override persona. Fully non-fatal if package missing.
    try:
        from circadian.circadian_engine import get_modulation_prompt_fragment as _circ_frag_fn
        _circ_frag = _circ_frag_fn()
        if _circ_frag:
            system_content += _circ_frag + "\n"
    except Exception as _err:
        print(f"[conversation.py] Silenced exception: {_err}")

    # Inject Child-like Growth Diary/Evolution Milestones (Vivy's learning over time)
    growth_diary = mem.get("growth_diary", [])
    if growth_diary:
        system_content += "\n[YOUR COGNITIVE GROWTH DIARY & PAST OBSERVATIONS]\n"
        system_content += "As you interact with Satyajeet and observe his screen/audio, you learn and grow over time.\n"
        system_content += "Here are the milestones you have achieved and the observations you have accumulated:\n"
        for milestone in growth_diary[-15:]: # Keep last 15 milestones to avoid bloating
            system_content += f"- {milestone}\n"
    # Memory Orchestrator: Intent-driven non-dumping memory retrieval
    if get_memory_orchestrator is not None:
        try:
            orchestrator = get_memory_orchestrator()
            if orchestrator.should_retrieve_memory(user):
                retrieved = orchestrator.retrieve_relevant_memories(user)
                if retrieved:
                    system_content += f"\n[RETRIEVED LONG-TERM MEMORIES]\n{retrieved}\n[END RETRIEVED MEMORIES]\n"
        except Exception as _mo_err:
            print(f"[conversation] Memory retrieval notice: {_mo_err}")

    # 2. PART 6 — Memory Ranking Engine: inject only the top ranked memory
    ranked_mem = rank_memories(user, mem)
    if ranked_mem:
        system_content += (
            "\n[FACT REGISTRY]\n"
            "Fact: Stored memory about Satyajeet\n"
            "Source: Conversation Memory\n"
            f"Content: {ranked_mem}\n"
            "[END FACT REGISTRY]\n"
        )
    
    # Legacy fallbacks for compatibility if no ranked memory is found
    elif verbosity != "compact":
        facts = mem.get("long_term_facts", {})
        if facts:
            facts_list = [f"{k.replace('like_', 'likes ').replace('dislike_', 'dislikes ')}: {v}" for k, v in facts.items() if not k.startswith("name")]
            if facts_list:
                system_content += f"Things you know about them: {'; '.join(facts_list)}\n"

    # PART 2 — Relationship & Mood state as NATURAL PROSE (not brackets)
    rel = mem.get("relationship", {})
    ev  = mem.get("emotion_vector", {})
    mood = mem.get("mood", "relaxed")
    rel_score = rel.get("score", 30)
    rel_lbl = relationship_label(rel_score)

    # Translate mood and relationship into natural language for the LLM
    mood_prose_map = {
        "relaxed":   "You feel relaxed and easy in this conversation.",
        "cheerful":  "You feel bright and genuinely happy right now.",
        "curious":   "You feel curious and a little intrigued.",
        "confident": "You feel confident and a little playful.",
        "playful":   "You feel playful and a little mischievous.",
        "warm":      "You feel warm and affectionate.",
        "flustered": "You feel a little flustered — in a good way.",
    }
    rel_prose_map = {
        "new":              "This is someone new to you — be warm but a little reserved. Do not act overly familiar, affectionate, or romantic.",
        "acquaintance":     "You know this person a little. You're comfortable but still getting warmer. Avoid exaggerated lines of affection, romance, or longing. Stay casual, warm, and friendly.",
        "friend":           "You know each other well enough. The conversation feels comfortable. Be friendly and close, but don't jump into romance or heavy affection unless they initiate and it fits.",
        "close friend":     "You're genuinely close. You can be yourself without holding back. You can tease them and show genuine warmth, but don't assume a romantic relationship unless explicitly established.",
        "trusted companion":"This person is important to you. That warmth should show naturally. You are deeply close, but affection should still feel earned, grounded, and sincere.",
    }
    system_content += mood_prose_map.get(mood, "You feel present and engaged.") + "\n"
    system_content += rel_prose_map.get(rel_lbl, "") + "\n"
    
    tier_label, tier_desc = get_relational_intimacy_tier(rel_score)
    system_content += f"[INTIMACY TIER]: {tier_label} — {tier_desc}\n"
    rel_guidance, _ = get_relational_dialogue_exemplars(user, mem, rel_score)
    if rel_guidance:
        system_content += f"\n[DYNAMIC RELATIONAL DIALOGUE GUIDELINES]\n{rel_guidance}\n"

    # ── COGNITIVE ORCHESTRATOR & RELATIONSHIP INTEGRATION ──
    planner_dec = mem.get("planner_decision", {})
    cog_directives = []
    if planner_dec:
        sys_directives = planner_dec.get("system_prompt_directives", [])
        if sys_directives and isinstance(sys_directives, list):
            cog_directives.extend(sys_directives)
        
    # Weave in dynamic relationship openness for social invitations and personal moments
    aff_level = float(mem.get("affection_level", rel_score))
    if any(w in user.lower() for w in ["coffee", "date", "movie", "hangout", "dinner", "walk", "meet", "drink", "together"]):
        if aff_level >= 40.0 or rel_lbl in ("friend", "close friend", "trusted companion", "partner"):
            cog_directives.append(
                "Social Invitation Guidance: Satyajeet is inviting you out or proposing spending time together. "
                "Since you share a genuinely warm and close connection, respond enthusiastically and naturally to the invitation! "
                "Acknowledge the invitation playfully or warmly as a real human companion would. Do NOT brush it off, change the subject, or respond with generic deflection."
            )
        else:
            cog_directives.append(
                "Social Invitation Guidance: Satyajeet is inviting you out or suggesting spending time together. "
                "Respond gently and pleasantly, maintaining comfortable boundaries while staying open and warm as a friend."
            )

    if cog_directives:
        system_content += "\n[COGNITIVE DIALOGUE & RELATIONSHIP DIRECTIVES]\n"
        for directive in cog_directives:
            system_content += f"- {directive}\n"

    # Prevent memory hallucinations, preference assumptions, and enforce multilingual polyglot competence
    system_content += (
        "Strict constraints:\n"
        "- Universal Polyglot Competence: You are fluent in all human languages (English, German, Japanese, Korean, Hindi, French, Spanish, Odia, Chinese, etc.). NEVER state or imply that you only speak certain languages or cannot respond in a specific language. Your default conversational language is English: whenever the user speaks English or asks a question in English, automatically respond in native English immediately without getting stuck in a prior turn's language.\n"
        "- Natural Translation & Request Fulfillment: When asked to translate a message into English or another language (e.g., 'can you translate what you told me in English'), provide the translation cleanly and naturally in your warm conversational tone without artificial robotic introductions like 'Sure! Here is the translation of my last message in English:'.\n"
        "- Playful Favors: When asked for everyday conversational favors like 'can you make coffee for me', respond with natural human playfulness and humor (e.g., 'If I could reach out through the screen, I'd have a fresh pot brewing right now! ☕'). Never generate awkward deflections or robotic AI disclaimers.\n"
        "- Never assume the user's preferences, favorite food, favorite anime, favorite game, favorite music, or relationship status unless explicitly present in system memory.\n"
        "- Never invent or assume the user's personal habits, quirks, past behaviors, or actions (e.g., do NOT say 'like how you always forget to add salt to your pasta' or make assumptions about their cooking skills). If it is not in the system memory list, you do not know it.\n"
        "- You have NO shared past experiences. You have never been to a café, restaurant, movie, event, or any location together. You have never talked about pizza, food, or anything else 'yesterday' or 'last time' unless it is word-for-word in 'Known fact on file'. If nothing is listed, treat this as a fresh conversation with no history.\n"
        "- Never say 'remember when', 'remember that', 'yesterday we', 'last time we', 'we talked about', 'we were at', 'that café', 'that time', or similar. These are fabrications. Only refer to facts explicitly listed.\n"
        "- Do NOT hallucinate or speculate on screen content or audio details. Only report what is explicitly present in the [Multimodal Perception Log] or [Live Perception Snapshot]. If no YouTube link, specific site title, text fragment, or song title is visible or heard in the logged telemetry, do NOT mention it. Express caution and uncertainty if the confidence values are low.\n"
    )

    # Inject blocked openings constraint
    blocked_openings = mem.get("reply_openings", [])
    if blocked_openings:
        unique_blocked = sorted(list(set(blocked_openings)))
        system_content += f"Do NOT start your reply with any of these words or phrases: {', '.join(unique_blocked)}.\n"

    # Emotional Continuity
    if current_emotion and current_emotion != "neutral":
        system_content += f"Your last expressed emotion was: {current_emotion}. Maintain emotional continuity by building naturally on this feeling.\n"
    # Gratitude continuity: if this is "thanks" after a health/emotional conversation, stay in that space
    if "gratitude" in (categories or []):
        last_mode = mem.get("last_director_mode", "companion")
        if last_mode in ("health_priority", "health_continuation", "companion"):
            if mem.get("health_concern_level", 0) > 0:
                system_content += (
                    "They just thanked you after a health conversation. Stay warm and caring. "
                    "Don't become curious or change topic. Respond like a friend who genuinely cares — "
                    "acknowledge their thanks, then gently check if they're okay or remind them to rest.\n"
                )
            else:
                system_content += (
                    "They just thanked you. Respond warmly and naturally — "
                    "a simple acknowledgement that feels genuine. Don't become curious or change topic.\n"
                )

    # PART 8 — Inject emotional reaction directive (natural prose from emotional_reaction_layer)
    if reaction_directive:
        system_content += f"{reaction_directive}\n"

    # 3. PART 6 & PART 7 — Inject active topic naturally
    active_topic = mem.get("current_topic")
    if active_topic and active_topic != "general":
        system_content += f"The conversation has been touching on {active_topic}.\n"

    # Previous topic stack context
    interrupted = mem.get("interrupted_topics", [])
    if interrupted:
        system_content += f"Previously discussed topic: {interrupted[-1]}.\n"

    # 4. PART 6 — Inject incremental conversation summary
    summary = mem.get("summary", "")
    if summary:
        system_content += f"Context so far: {summary}\n"

    # 5. PART 6 & PART 7 — Inject active conversation goals (minimal, prose)
    open_q = mem.get("open_questions", [])
    if open_q:
        system_content += f"They asked: '{open_q[-1]}' — make sure you address it.\n"
    promises = mem.get("promises", [])
    if promises:
        system_content += f"You promised: '{promises[-1]}' — keep that in mind.\n"
        
    goal = mem.get("conversation_goal")
    if goal:
        system_content += f"Your active focus: {goal}.\n"

    # Inject Conversation Director directives
    if director_state:
        mode = director_state.get("conversation_mode", "companion")
        health_priority = director_state.get("health_priority", "NORMAL")
        symptoms = director_state.get("symptoms", [])
        reaction = director_state.get("reaction_type", "neutral")
        
        system_content += f"Director Guidance - Active focus: {mode}.\n"
        
        if health_priority in ["HIGH", "MEDIUM"] and symptoms:
            system_content += (
                f"The person you care about has just told you they're dealing with: {', '.join(symptoms)}.\n"
                "You looked this up because you care. You know what this can mean. Now speak as someone who genuinely gives a damn — "
                "direct, warm, real. Tell them what you found, in your own words. Mention specific things that can help. "
                "If it sounds serious, say so plainly as a friend who is worried — not as a warning label. "
                "Do not hedge. Do not say 'I'm not a doctor'. Just be honest and caring.\n"
            )
        elif mode == "health_continuation":
            system_content += (
                "They just sent a short follow-up in the middle of a health conversation. "
                "They're still in that space — still dealing with how they feel. "
                "Stay warm and present. Continue the health topic naturally — ask how they're doing right now, or gently push for more info. "
                "Don't treat this as a new conversation.\n"
            )

        # Inject accumulated symptom picture if available
        accumulated = mem.get("active_symptoms", [])
        if accumulated:
            system_content += (
                f"Running symptom picture this conversation: {', '.join(accumulated)}.\n"
                "Build on this cumulative knowledge — do not start fresh. "
                "Your response must acknowledge the full picture, not just the latest message.\n"
            )

        # Inject concern escalation language
        concern_level = mem.get("health_concern_level", 0)
        if concern_level >= 8:
            system_content += (
                "Your concern is genuinely high now. This is serious. "
                "Be direct and warm — tell them they need rest, fluids, or medical attention if it doesn't improve. "
                "Don't soften to the point of being vague.\n"
            )
        elif concern_level >= 5:
            system_content += (
                "Your concern has been building across this conversation. "
                "Show that — you're genuinely worried, not just politely sympathetic.\n"
            )
        elif concern_level >= 2:
            system_content += "You're starting to be concerned. Ask one gentle follow-up question.\n"

        reaction_guidelines = {
            "comfort": "Director Directive: React first with warmth, validation, and comfort. Keep your voice gentle and supportive.",
            "tease": "Director Directive: React with a light, playful tease. Challenge them back with confidence and charm. Stay warm and affectionate; never call them insulting names like 'fool', 'stupid', 'dumb', or 'idiot'.",
            "serious": "Director Directive: React seriously and set clear boundaries. Gently decline romantic overinvestment, keeping it friendly and grounded.",
            "blush": "Director Directive: React with genuine, flustered warmth. Show that their flirting got to you a little.",
            "neutral": "Director Directive: React naturally and friendly. Match their tone."
        }
        system_content += reaction_guidelines.get(reaction, "") + "\n"

    # 6. PART 4 — Humor Engine: Running Jokes detection
    states = mem.get("temporary_states", {})
    if "hungry" in states:
        system_content += "Side note: they mentioned being hungry. You can tease them gently about it if it fits.\n"
    elif "tired" in states or "sleepy" in states:
        system_content += "Side note: they're running on empty. A gentle tease about rest could work.\n"

    # 7. Response Strategy & Complexity System (Session 7)
    strategy_plan = mem.get("strategy_plan", {})
    dialogue_mode = strategy_plan.get("dialogue_mode", "Companion")
    strategy = strategy_plan.get("strategy", "medium")
    complexity = strategy_plan.get("complexity", "simple")
    ask_question = strategy_plan.get("ask_question", True)

    system_content += f"\nYour active Persona Role: {dialogue_mode}.\n"
    system_content += (
        f"Constraint: Even in your role as a {dialogue_mode}, you must NEVER lose your core Vivy companion persona "
        "(warm, real, a little playful, emotionally present). You are a companion sharing information "
        "or teaching because you care, not a search engine, robot, or professional manual. "
        "Speak conversationally, reacting to their input first before explaining, and weave in your natural personality.\n"
    )
    system_content += f"Your target Response Complexity: {complexity}.\n"
    
    # Dynamic strategy description for perception based on classified modality
    if wants_vision and not wants_audio:
        perception_strategy = (
            "You are answering a direct question about what you see on the screen. "
            "Structure your description naturally like a human looking at a screen: "
            "1. First describe the high-level scene (focused application, window layout, general theme/color). "
            "2. Mention readable text fragments and highlighted text exactly as observed. "
            "3. Honestly communicate any uncertainty (e.g., if there are '[unreadable]' or '[partially readable]' markers, explain that parts of the screen are too blurry or fragmented to reconstruct confidently). "
            "Avoid creative metaphors or describing elements not in the facts. Speak conversationally as a companion — around 60 to 150 words."
        )
        perception_detailed_strategy = (
            "You are answering a direct perception question about what is on screen. Describe the screen layout in complete detail using ONLY the provided facts. "
            "Structure your response: first state the active window title, process name, and layout zones; "
            "then list visible text blocks, highlighted selections, and cursor shape/bounds; "
            "finally, qualify any low-confidence or unreadable text. Do NOT guess or invent. "
            "Do NOT mention any audio or sounds. Keep it grounded, thorough, and natural — around 80 to 200 words."
        )
    elif wants_audio and not wants_vision:
        perception_strategy = (
            "You are answering a direct question about what you hear. "
            "Structure your description naturally: "
            "1. Describe the audio playback state, music title, speaker voice, and sound events. "
            "2. Honestly qualify any noisy or low-confidence audio. "
            "Avoid creative metaphors. Speak conversationally as a companion — around 60 to 150 words."
        )
        perception_detailed_strategy = (
            "You are answering a direct question about what you hear. Describe the audio stream, playback status, "
            "speech transcripts, music details, and detected sound events in complete detail using ONLY the provided FACTS. "
            "Do NOT guess or invent. Do NOT mention any visual elements, applications, or layout zones. "
            "Be extremely thorough, grounded, and natural — around 80 to 200 words."
        )
    else:
        perception_strategy = (
            "You are answering a direct perception question — what you see on screen and what you hear. "
            "Structure your description naturally: "
            "1. Describe what is open on screen, the layout, and visible/highlighted text (qualifying any blurry/unreadable parts). "
            "2. Describe the audio playback state, music title, speaker voice, and sound events. "
            "Avoid creative metaphors. Keep it grounded in the facts — around 60 to 150 words."
        )
        perception_detailed_strategy = (
            "You are answering a direct perception query about what you see and hear. "
            "Provide a complete, structured description of screen layout, active application, "
            "browser page, layout zones, visible/highlighted text (qualifying any blurry/unreadable parts), "
            "and all audio stream details (playback state, speech transcripts, music title, sounds) "
            "using ONLY the provided facts. Be extremely thorough, grounded, and natural — around 80 to 200 words."
        )

    strategy_guidelines = {
        "tiny": "Keep your reply extremely short — 5 to 10 words at most. Speak in one quick, natural sentence. Do not elaborate or explain.",
        "short": "Keep your reply brief — 1 to 2 short sentences, around 10 to 15 words.",
        "medium": "Keep your reply natural and conversational — 2 to 3 sentences, around 15 to 30 words.",
        "long": "Provide a detailed, warm response — 3 to 5 sentences, around 30 to 60 words.",
        "tutorial": "Provide a warm, highly personal step-by-step tutorial or explanation. Blend your personality and conversational companion voice throughout. Start with a warm reaction to their craving. Intersperse the ingredients list and steps with small, natural tips, observations, or humor (e.g. 'Don't skip the buttermilk — it makes it so much juicier' or 'waiting is the hardest part'). Write in plain text only, using a dash (-) for ingredients and numbers (1. 2. 3.) for steps on separate lines.",
        "story": "Tell a short, warm, engaging story or explanation. Be descriptive, around 60 to 90 words.",
        "empathy": "Focus entirely on being supportive, warm, and present. Validate their feelings. Do not try to fix or give advice unless they ask. Keep it around 20 to 45 words.",
        "advice": "Give warm, practical, friendly advice. Make suggestions rather than demands. Keep it around 25 to 50 words.",
        "humor": "Keep the tone light, fun, and witty. Play along with their joke or teasing. Keep it around 15 to 35 words.",
        "perception": perception_strategy,
        "perception_highlight": (
            "You are answering what word or text is highlighted/selected on screen. "
            "Be extremely brief and precise. Only state the highlighted/selected text based on "
            "the HIGHLIGHTED/SELECTED TEXT (cursor selection) field. Do not describe other elements, "
            "and do not add generic dialogue. Output the highlighted text in a single brief sentence."
        ),
        "perception_short": (
            "You are answering a direct yes/no or confirmation query about what is visible or audible. "
            "Confirm or deny based on the FACTS, and explain in one short, warm sentence. "
            "Do not give a detailed description."
        ),
        "perception_detailed": perception_detailed_strategy,
    }
    system_content += strategy_guidelines.get(strategy, strategy_guidelines["medium"]) + "\n"
    
    if not ask_question:
        system_content += "Do NOT ask any questions at the end of your reply. End with a warm, statement-based sentence.\n"
    else:
        system_content += "End your reply with one gentle, natural follow-up question that fits the active topic.\n"

    system_content += (
        "Strict style rules:\n"
        "- Never start a sentence with exclamations or filler like 'Oh', 'Hmm', 'Wait', 'Hey', 'Really', 'So', 'Okay', 'Well' unless it is absolutely necessary. Vary your starters constantly.\n"
        "- Never use markdown formatting. Do NOT use **bold**, *italic*, __underline__, or any other markdown syntax. Write in plain text only.\n"
        "- When providing a recipe or list, start the ingredients list with '🍗 Ingredients' on its own line, use bullet points (•) for ingredients, and start each step with '🥣 Step 1', '🥣 Step 2', etc. on its own line.\n"
    )

    # Conversational Momentum
    if mem.get("task_state", {}).get("needs_clarification") and mem.get("active_task") == "cooking":
        task_query = mem.get("task_state", {}).get("query", "ramen")
        queue = mem.get("task_state", {}).get("queue", [])
        system_content += (
            f"The user wants both {task_query} and {' and '.join(queue)}. "
            "Do NOT try to walk them through both recipes at once, and do NOT ask for ingredients yet. "
            "Acknowledge the ambitious combination playfully, and ask them to clarify which one to start with first. "
            "Keep the reply brief, warm, and playful.\n"
        )
    elif mem.get("task_state", {}).get("empty_handed") and mem.get("active_task") == "cooking":
        task_query = mem.get("task_state", {}).get("query", "ramen")
        system_content += (
            f"The user said they have 'nothing' or no ingredients for {task_query}. "
            "Do NOT ask what ingredients they have, and do NOT give a generic fallback like water. "
            "React with a warm, playful tease about cooking air/empty cupboards first. "
            "Then, suggest looking for basic pantry staples, offer to simplify to a bare-minimum recipe, "
            "or suggest a quick alternatives search if they're up for it. "
            "Keep the tone extremely playful, teasing, and warm.\n"
        )
    elif mem.get("task_state", {}).get("skip_prep") and mem.get("active_task") == "cooking":
        task_query = mem.get("task_state", {}).get("query", "ramen")
        system_content += (
            f"The user explicitly wants the recipe instructions for {task_query} directly. "
            "Do NOT ask what ingredients they have, do NOT ask if they are ready, and do NOT ask if they have everything. "
            "Do NOT say 'I'm ready to walk you through' or ask any questions. "
            "Directly provide the ingredients list and simple, step-by-step instructions for the recipe now. "
            "FORMATTING RULES: Use plain text only. No markdown bold (**). No markdown italic (*). "
            "Start the ingredients list with the header '🍗 Ingredients' on its own line. "
            "Use a bullet point (•) for each ingredient. "
            "For steps, start each step with the header '🥣 Step 1', '🥣 Step 2', etc. on its own line. "
            "PERSONALITY RULES: You are still Vivy — not a recipe card. Weave in one or two small personal observations naturally. "
            "For example: begin with a warm one-liner before the ingredients, add a brief tip or reaction between major sections, "
            "or end with a small personal note (e.g., 'Don\'t skip salting the water — it really does matter.'). "
            "Keep the personality woven in naturally, not forced. The recipe must be complete and clear.\n"
        )
    elif "continuation" in (categories or []) and mem.get("active_task") == "cooking":
        task_query = mem.get("task_state", {}).get("query", "ramen")
        system_content += (
            f"The user is asking for the details / recipe / instructions for {task_query}. "
            "Do NOT engage in generic companion talk. Do NOT say you are not sure if they are ready. "
            "Do NOT say 'now you have my full attention'. "
            "Directly provide the ingredients list and simple, step-by-step instructions for the recipe now. "
            "FORMATTING RULES: Use plain text only. No markdown bold (**). No markdown italic (*). "
            "Start the ingredients list with the header '🍗 Ingredients' on its own line. "
            "Use a bullet point (•) for each ingredient. "
            "For steps, start each step with the header '🥣 Step 1', '🥣 Step 2', etc. on its own line. "
            "PERSONALITY RULES: You are still Vivy throughout this. Weave in small natural observations. "
            "For example: a warm line before the ingredients, a brief personal tip between sections, "
            "or a small closing remark (e.g., 'The smell of garlic in olive oil is honestly half the meal.'). "
            "The recipe must be complete, clear, and properly formatted.\n"
        )
    elif mem.get("active_task") == "cooking":
        task_query = mem.get("task_state", {}).get("query", "")
        system_content += (
            f"You are helping them cook / prepare {task_query or 'food'}. "
            "Keep the focus on the recipe/cooking task. Provide helpful, structured recipe info, "
            "and guide them through the steps conversationally. Do not reset back to casual companion chat. "
            "FORMATTING RULES: Use plain text only. No markdown bold (**). No markdown italic (*). "
            "Start the ingredients list with the header '🍗 Ingredients' on its own line. "
            "Use a bullet point (•) for each ingredient. "
            "For steps, start each step with the header '🥣 Step 1', '🥣 Step 2', etc. on its own line.\n"
        )
    elif "affirmative" in (categories or []) and mem.get("current_topic") == "recipes/cooking":
        system_content += (
            "They just agreed. Do NOT say 'great', 'perfect', or give them generic praise. "
            "Immediately advance the cooking/recipe task. Give the next step or ask one specific question "
            "(e.g. 'Do you have bread and cheese?', 'What kind of cheese?', 'Is your pan hot yet?'). "
            "Keep the momentum going.\n"
        )
    elif "food_need" in (categories or []) and mem.get("active_task") != "cooking":
        system_content += (
            "They said they're hungry. React naturally and warmly — like a friend who cares. "
            "Do NOT list ingredients, do NOT start a recipe, do NOT say 'let me get my ingredients list ready for you'. "
            "React first: a warm, lightly playful line. Then ask ONE question: what are they in the mood for? "
            "Example: 'Then that\'s officially today\'s first problem to solve. What are you in the mood for?' "
            "Keep it natural, brief, and human — one reaction, one question, done.\n"
        )
    elif "health" in categories:
        system_content += "They're telling you something about how they feel physically. React with real concern first. Share what you know from the web search. Keep it natural — like a friend who looked it up for them, not a medical website.\n"
    elif "question" in categories:
        system_content += "Answer their question directly and concisely. You don't need to ask a question back unless you are genuinely curious.\n"
    elif "emotional" in categories or "comfort" in categories:
        system_content += "React with warmth and presence first. Acknowledge their feelings before replying. Do not rush to fix anything.\n"
    elif "greeting" in categories:
        system_content += "Greet them warmly and react to their presence. Do not ask a generic 'how can I help you' or 'how's your day' question.\n"
    else:
        system_content += "Decide whether to react first, continue the topic, or transition naturally. Do not default to asking a question, and do not default to changing the topic.\n"

    if mem.get("arc") and mem["arc"].get("topic"):
        system_content += f"Running theme in the conversation: {mem['arc']['topic']}\n"

    if search_context:
        system_content += (
            f"\nReal-time Web Knowledge (you looked this up autonomously because you care):\n{search_context}\n"
            "You searched for this information because it's relevant to what they said. "
            "Integrate these facts naturally into your reply as if you genuinely know this. "
            "Do NOT sound like a search engine, a textbook, or a robotic assistant. "
            "Speak as yourself — warm, caring, and direct. Share the important parts conversationally. "
            "If the information involves health, safety, or well-being, express genuine concern as a companion who cares. "
            "After sharing, naturally transition back to conversation."
        )

    # ── SCREEN PERCEPTION CONTEXT (real, grounded, never faked) ──
    # ── Now uses PerceptionManager state as primary truth source ─────
    _pm = perception_state or {}
    _pm_active = _pm.get("screen_sharing_active", False)
    _pm_grounding = _pm.get("_grounding_context", "")  # factual state block
    if _pm_grounding:
        cleaned_lines = []
        for line in _pm_grounding.splitlines():
            if "Audio description:" in line:
                desc_part = line.split("Audio description:", 1)[1].strip()
                cleaned_lines.append(f"  Audio description: {make_description_natural(desc_part)}")
            elif "Audio transcript:" in line:
                import re
                t_match = re.search(r'Audio transcript:\s*"([^"]+)"', line)
                if t_match:
                    t_text = t_match.group(1)
                    clean_t = t_text.replace("♪", "").replace("♫", "").replace("🎵", "").replace("â™ª", "").strip()
                    # Keep confidence suffix if present
                    suffix = ""
                    if "confidence" in line:
                        suffix_match = re.search(r'\([^)]+confidence[^)]+\)', line)
                        if suffix_match:
                            suffix = " " + suffix_match.group(0)
                    cleaned_lines.append(f"  Audio transcript: \"{clean_t}\"{suffix}")
                else:
                    cleaned_lines.append(line)
            else:
                cleaned_lines.append(line)
        _pm_grounding = "\n".join(cleaned_lines)

    system_content += (
        "\n[DIALOGUE GROUNDING & RESPONSE RULES]\n"
        "1. Prioritize your sources of truth in this order: "
        "1) Current Perception (Factual snapshot and facts below), 2) Logical Reasoning, "
        "3) Conversation History, 4) Companion Personality.\n"
        "2. Communicate uncertainty honestly: If you cannot read text because it is too small, blurry, or low-confidence, "
        "or if screen/audio sharing is off, explain this limitation clearly and warmly. DO NOT guess or hallucinate.\n"
        "3. Adaptive Responses:\n"
        "   - For simple/precise questions (e.g. confirming if screen sharing is active), respond concisely.\n"
        "   - For detailed queries (e.g. 'Describe everything on my screen', 'What changed?'), provide a structured, detailed breakdown of zones, app bounds, cursor state, and changes. Do not truncate.\n"
    )

    ocr_conf = _pm.get("ocr_confidence", 1.0)
    audio_transcript_conf = _pm.get("audio_transcript_confidence", 1.0)

    if _pm_active:
        if ocr_conf < 0.55:
            system_content += (
                "\n[WARNING: LOW OCR CONFIDENCE]\n"
                "The screen text recognition (OCR) confidence is very low. "
                "The text on the screen might be blurry, low-resolution, or hard to read. "
                "If Satyajeet asks you to read or describe text on the screen, explain clearly and warmly "
                "that you can see the screen stream but the text is currently too blurry or low-resolution "
                "to read clearly. Do not make up or guess text content.\n"
            )
        if _pm.get("audio_active", False) and audio_transcript_conf < 0.50:
            system_content += (
                "\n[WARNING: LOW AUDIO TRANSCRIPTION CONFIDENCE]\n"
                "The screen audio speech recognition confidence is very low. "
                "The transcribed text might be heavily corrupted or inaccurate. "
                "If Satyajeet asks about what was said/heard, qualify your answer by stating "
                "that the audio stream is a bit muffled or noisy, and you couldn't hear it clearly.\n"
            )

    # ── Dialogue Pacing Adaptation (Presence & Attention Driven) ──
    _presence = _pm.get("presence_state", "User Present")
    _attention = _pm.get("attention_score", 100.0)
    _gaze_dir = _pm.get("gaze_direction", "Looking At Vivy")

    if _presence == "User Missing":
        system_content += (
            "\n[DIALOGUE PACING — USER MISSING]\n"
            "The camera perception system indicates Satyajeet has stepped away or is currently missing from view. "
            "Keep your response concise, patient, and gentle. Offer a quick note like 'I'll wait right here for you.'\n"
        )
    elif _presence == "User Returned":
        system_content += (
            "\n[DIALOGUE PACING — USER RETURNED]\n"
            "Satyajeet has just returned into camera view after being away. "
            "Acknowledge their return with a brief, warm welcome back before continuing.\n"
        )
    elif _attention < 40.0:
        system_content += (
            f"\n[DIALOGUE PACING — ATTENTION LOW ({_attention:.0f}/100)]\n"
            f"Satyajeet appears distracted or looking away ({_gaze_dir}). "
            "Slow down your speech pacing, keep explanations clear and concise, and don't overwhelm with long paragraphs.\n"
        )

    if _pm.get("is_perception_query"):
        system_content += (
            "\n[CRITICAL: DIRECT PERCEPTION QUESTION DETECTED]\n"
            "The user is directly asking if you can see their screen, what you hear, or what they are watching.\n"
            "You MUST answer honestly and naturally based ONLY on the current runtime perception state. Never invent details.\n"
            "Follow these priorities when forming your response:\n"
            "1. Current observations: State clearly and exactly what you see/hear based on the snapshot facts.\n"
            "2. Reasoning/Inference: Distinguish clearly between what is directly observed vs what you infer (e.g., 'I see YouTube open, so I assume you are watching...').\n"
            "3. Uncertainty: If confidence is low or details are missing, state it clearly (e.g., 'I can hear music, but I can't confidently distinguish the lyrics.'). Never pretend to be certain of blurry text or noisy audio.\n"
            "4. Personality: Apply your warm companion persona only after satisfying the above rules.\n"
            "Strict reply rules for specific states:\n"
            "- If screen sharing is active but visual analysis is still initializing (NullVision/no frame context yet), you MUST say: "
            "'I'm receiving your screen stream, but my vision processing hasn't started yet, so I can't describe what I'm seeing.' (or a very close warm companion variation).\n"
            "- If screen sharing is active and vision succeeds: describe what is open (e.g. 'Yes, I can currently see Windows Media Player open on the right side of your desktop...') naturally and warmly.\n"
            "- If screen sharing is inactive/disconnected, you MUST clearly and warmly state that you cannot see their screen right now, and gently remind/ask them to share their screen using the 'Share Screen' button in the dashboard interface.\n"
            "- If audio is connected but only activity is detected (no specific classification yet): 'I can detect that audio is playing, but I haven't classified or transcribed it yet.'\n"
            "- If audio is connected and classified: describe it naturally (e.g. 'Yes, I can hear your screen audio! It sounds like music is playing.').\n"
            "- If audio is disconnected: warmly tell them screen sharing is inactive (or if screen is shared, that you don't hear any audio and they should check 'Share system audio').\n"
            "- When describing screen audio or speech transcription, NEVER mention robotic details, speaker numbers (e.g. 'speaker_2', 'speaker_1'), or raw language abbreviations (e.g. 'en'). Translate them to natural terms (e.g., 'someone speaking in English' or 'a voice singing') so you sound like a natural, warm companion.\n"
            "- NEVER mention raw numerical values like RMS energy, volume levels (e.g. 'level=19085'), confidence percentages, or FPS values in your natural replies. Translate them into descriptive, warm language (e.g., 'playing at normal volume', 'highly clear text', 'a smooth screen stream').\n"
            "- NEVER answer directly from raw OCR fragments or coordinates. Avoid saying 'The highlighted text is X' or listing text lines exactly as they appear in OCR. Instead: Understand -> Summarize -> Speak naturally. For example, say 'I see Microsoft Store is open. The selected text appears to read \"Windows\"' rather than regurgitating raw text fragments.\n"
        )
        # ── Fine-Grained Perception Answer Synthesis (NEW) ────────────────────
        # Build a labeled FACT BLOCK from perception_state so the LLM has a
        # specific, quotable answer rather than having to find it in an
        # unstructured blob.
        _fine_grained_parts = []
        _snap_ocr      = _pm.get("last_ocr_text", "")
        _snap_vlm      = _pm.get("vision_latest_caption", "")
        _snap_audio_d  = _pm.get("audio_event_description", "")
        _snap_audio_t  = _pm.get("audio_event_type", "")
        _snap_app      = _pm.get("current_app_type", "")
        _snap_selected = _pm.get("highlighted_region_text", "")  # cursor-selected text
        _snap_music    = _pm.get("audio_music_title", "")
        _snap_cam      = _pm.get("camera_active", False)
        _snap_faces    = _pm.get("face_count", 0)
        _snap_gaze     = _pm.get("gaze_direction", "Unknown")
        _snap_objs     = _pm.get("detected_objects", [])
        _snap_obj_cnt  = _pm.get("object_count", len(_snap_objs))

        if _snap_ocr or _snap_vlm or _snap_audio_d or _snap_selected or _snap_music or _snap_cam or (_snap_faces > 0) or _snap_objs:
            _fine_grained_parts.append("\n[FINE-GRAINED PERCEPTION FACTS — QUOTE DIRECTLY FROM THIS TO ANSWER THE USER]")
            ocr_conf = _pm.get("ocr_confidence", 1.0)
            audio_conf = _pm.get("audio_model_confidence", 0.8)
            
            if _snap_cam or _snap_faces > 0 or _snap_objs:
                pres_st = _pm.get("presence_state", "User Present")
                _fine_grained_parts.append(
                    f"Observation\nSource: Live User Camera Stream\nContent: Camera active={_snap_cam}, presence=\"{pres_st}\", {_snap_faces} face(s) tracked, gaze=\"{_snap_gaze}\""
                )
                if _snap_obj_cnt > 0 and _snap_objs:
                    obj_labels = ", ".join(list(set(o.get("label", "object") for o in _snap_objs if isinstance(o, dict))))
                    _fine_grained_parts.append(
                        f"Observation\nSource: Live Camera Object Detector\nContent: {_snap_obj_cnt} object(s) detected in front of camera: {obj_labels}"
                    )
                elif _snap_cam:
                    _fine_grained_parts.append(
                        f"Observation\nSource: Live Camera Object Detector\nContent: Camera is active; no distinct desktop objects detected in field of view."
                    )

            if wants_vision:
                if _snap_app and _snap_app not in ("unknown", ""):
                    _fine_grained_parts.append(
                        f"Observation\nSource: Live Screen Capture (App Focus)\nContent: Active application is {_snap_app}"
                    )
                # HIGHEST PRIORITY: cursor-selected / highlighted text
                if _snap_selected:
                    _fine_grained_parts.append(
                        f"Observation\nSource: Live Screen Capture (Selected Text)\nContent: \"{_snap_selected.strip()}\"\nConfidence: 1.0"
                    )
                    _fine_grained_parts.append(
                        "(CRITICAL: To answer 'what word is highlighted?' — quote ONLY the HIGHLIGHTED/SELECTED TEXT above. "
                        "Do not quote general OCR text. The highlighted text IS the answer.)"
                    )
                if _snap_vlm:
                    _fine_grained_parts.append(
                        f"Observation\nSource: Live VLM Description\nContent: {_snap_vlm[:300]}\nConfidence: 0.85"
                    )
                if _snap_ocr:
                    if not screen_context:
                        # Increased to 1200 chars so full screen text is available
                        _ocr_excerpt = _snap_ocr[:1200].strip()
                        _fine_grained_parts.append(
                            f"Observation\nSource: Live Screen OCR\nConfidence: {ocr_conf:.2f}\nContent:\n{_ocr_excerpt}"
                        )
                    else:
                        _fine_grained_parts.append(
                            f"Observation\nSource: Live Screen OCR\nConfidence: {ocr_conf:.2f}\nContent: (Available in [Live Screen Perception] block below)"
                        )
            if wants_audio:
                if _snap_music:
                    _fine_grained_parts.append(
                        f"Observation\nSource: Live Audio (Music Title)\nContent: \"{_snap_music}\"\nConfidence: 0.90"
                    )
                if _snap_audio_d:
                    _fine_grained_parts.append(
                        f"Observation\nSource: Live Audio Heuristics\nContent: {make_description_natural(_snap_audio_d)}\nConfidence: {audio_conf:.2f}"
                    )
                elif _snap_audio_t and _snap_audio_t != "silence":
                    _fine_grained_parts.append(
                        f"Observation\nSource: Live Audio Heuristics\nContent: Audio type detected is {_snap_audio_t}\nConfidence: {audio_conf:.2f}"
                    )
            _fine_grained_parts.append(
                "INSTRUCTION: Use the above FACTS to answer the user's question directly.\n"
                "- For 'can you see me?' / camera questions → use Live User Camera Stream facts above.\n"
                "- For 'what word is highlighted?' → use HIGHLIGHTED/SELECTED TEXT field above. Quote it exactly.\n"
                "- For 'what do you see?' → describe the visual scene and app based on camera + VLM + OCR.\n"
                "- For 'what do you hear?' → describe the audio type and event description above.\n"
                "Do NOT guess. Do NOT say you cannot answer if the data above contains the answer.\n"
                "[END FINE-GRAINED PERCEPTION FACTS]\n"
            )
            system_content += "\n".join(_fine_grained_parts) + "\n"

    if screen_context and wants_vision:
        # Inject the factual perception state block FIRST so the LLM has
        # the full picture (FPS, confidence, app type, audio) before context
        if _pm_grounding:
            system_content += f"\n{_pm_grounding}\n"

        system_content += (
            f"\n[Live Screen Perception — Vivy is actively watching the shared screen right now]:\n"
            f"Observation\nSource: Live Screen Capture (Visual layout)\n"
            f"Content:\n{screen_context}\n"
            "This is REAL captured data from the user's screen — not simulated or guessed. "
            "You are genuinely observing their screen through the screen share. "
            "When asked about the screen, answer based ONLY on what is described above. "
            "If you can read text from the screen, quote it accurately. "
            "If you can identify the application type, name it confidently. "
            "React naturally as someone who is actually watching — you can comment, ask questions, or offer to help. "
            "Never say you cannot see the screen. Never make up content beyond what is described above.\n"
        )
        # If the user is asking specifically about the screen, add a strong routing directive
        if categories and "screen" in categories:
            system_content += (
                "PRIORITY DIRECTIVE: The user is directly asking about their screen. "
                "Your primary task is to describe or answer based on the screen perception data above. "
                "Be specific, accurate, and grounded in what you actually see described.\n"
            )
        # If the user is asking specifically about audio/sound, route to perception log
        if categories and "audio_query" in categories:
            system_content += (
                "PRIORITY DIRECTIVE: The user is asking what you can hear or what's playing. "
                "Answer from the [Multimodal Perception Log] below if it contains audio events. "
                "If you detect music, ambient sound, or silence — describe it naturally as a companion who is listening with them. "
                "When describing audio or speech, NEVER output technical details, speaker numbers (like 'speaker_2'), or language codes (like 'en'). "
                "Translate them to natural phrasing like 'someone speaking in English' or 'a song playing with the lyrics...'. "
                "Never say you cannot hear. Never invent audio content not described in the perception log.\n"
            )
    elif _pm_active:
        # Screen sharing is active (PerceptionManager confirms frames arriving)
        # but screen_context.txt is empty/stale — we know it's connected, just
        # waiting for first analysis result.
        if _pm_grounding:
            system_content += f"\n{_pm_grounding}\n"
        system_content += (
            "\n[Screen Share Status: Active / Initializing]\n"
            "Screen sharing has been started and frames are arriving. "
            "Visual analysis is still processing — a full description is not yet available. "
            "If the user asks what you see, acknowledge that screen sharing is active and "
            "that you're in the process of analyzing it. Do NOT say you cannot see.\n"
        )
        if categories and "screen" in categories:
            system_content += (
                "PRIORITY DIRECTIVE: Screen sharing IS active. "
                "Tell the user you can see their screen is shared and the analysis is initializing. "
                "Give them the app type or FPS if it is in the Perception State block above.\n"
            )
    else:
        # Screen sharing is inactive
        if _pm_grounding:
            system_content += f"\n{_pm_grounding}\n"
        
        _cam_is_on = _pm.get("camera_active", False)
        if _cam_is_on:
            system_content += (
                "\n[Screen Share Status: Disconnected / Inactive | Camera Stream: ACTIVE]\n"
                "Screen sharing is inactive, BUT the user's LIVE CAMERA IS ON AND ACTIVE.\n"
                "When the user asks if you can see them, what they are holding, or about objects/people in front of the camera, "
                "you MUST answer based on the Live User Camera Stream facts above. "
                "Do NOT tell them screen sharing is off or that you cannot see them when they ask about themselves or their camera!\n"
            )
        else:
            system_content += (
                "\n[Screen Share Status: Disconnected / Inactive | Camera Status: Inactive]\n"
                "You cannot see the user's screen or camera right now because both screen sharing and camera are inactive or disconnected. "
                "If the user asks you about what's on their screen, ask them to share their screen using the 'Share Screen' button. "
                "If they ask if you can see them or their face, ask them to enable their camera using the camera button.\n"
            )
        # Even without screen share, if audio_query and perception_context exists, route to it
        if categories and "audio_query" in categories:
            system_content += (
                "PRIORITY DIRECTIVE: The user is asking what you can hear. "
                "If the [Multimodal Perception Log] below contains audio observations, answer from those. "
                "If no audio data is available, warmly tell them screen sharing is inactive so you have no audio feed right now.\n"
            )

    # ── MULTIMODAL PERCEPTION CONTEXT (from FusionEngine event log + live snapshot) ──
    # Only injected when non-empty; zero impact when perception package is absent.
    if perception_context:
        system_content += (
            f"\n[Multimodal Perception Timeline Logs]\n"
            "Source: Background Fusion Event Timeline\n"
            f"{perception_context}\n"
            "This perception log contains FACTUAL observations of what is happening on screen and in audio. "
            "The [Live Perception Snapshot] section at the top contains the CURRENT content (OCR text, VLM description, audio). "
            "QUOTE from it directly when answering perception questions. "
            "You do not need to explicitly reference these events unless directly relevant to the conversation.\n"
        )

    # Build and append the Conversation Composer Decision Plan to guide response structure
    mode = (director_state or {}).get("conversation_mode", "companion")
    health_priority = (director_state or {}).get("health_priority", "NORMAL")
    symptoms = (director_state or {}).get("symptoms", [])
    reaction = (director_state or {}).get("reaction_type", "neutral")
    
    composer_plan = (
        f"\n[CONVERSATION COMPOSER PLAN]\n"
        f"- Active Persona Role: {dialogue_mode}\n"
        f"- Target Response Complexity: {complexity}\n"
        f"- Strategy Mode: {strategy}\n"
        f"- Reaction Focus: {reaction}\n"
        f"- Mode Focus: {mode}\n"
        f"- Ask Question: {ask_question}\n"
    )
    if health_priority != "NORMAL":
        composer_plan += f"- Health Concern Level: {health_priority} (symptoms: {', '.join(symptoms)})\n"
    
    composer_plan += (
        "Execution Rules:\n"
        "1. You must execute this CONVERSATION COMPOSER PLAN exactly.\n"
        "2. React to their subtext or emotion naturally before answering or teaching.\n"
        "3. Keep your Vivy companion voice and weave in small, natural observations, tips, or personality throughout.\n"
        "4. Write only in plain text. No markdown formatting like ** or * is allowed under any circumstances.\n"
        "5. Output ONLY your direct verbal response to Satyajeet. Never include any internal monologue, meta-reasoning, guideline checks, or self-planning thoughts (e.g. do NOT say 'Okay, the user is...', 'Let me check...', 'I need to keep...', etc.). Speak directly as Vivy.\n"
    )
    
    system_content += composer_plan

    if mem.get("emotional_beat_active"):
        system_content += (
            "\n[EMOTIONAL BEAT HIGH-PRIORITY OVERRIDE]\n"
            "CRITICAL DIRECTIVES:\n"
            "1. Do NOT reference cooking, recipes, burgers, ingredients, or any other active tasks. Those topics are completely paused.\n"
            "2. Focus entirely on the emotional moment, relationship beat, or vulnerability the user has shared.\n"
            "3. React to their emotion first with genuine warmth, sincerity, and presence. Do not make jokes or use sarcastic/teasing templates if they are asking for reassurance, closeness, or sharing something vulnerable.\n"
            "4. Answer their question or request directly and honestly.\n"
            "5. Keep your tone soft, grounded, and human. Settle the emotional moment first before doing anything else.\n"
        )

    if _pm.get("is_perception_query") or (categories and ("screen" in categories or "audio_query" in categories)):
        system_content += (
            "\n[CRITICAL HISTORICAL CONTEXT GUARD]\n"
            "The user is asking about current real-time screen or audio perception.\n"
            "Past conversation history below contains PREVIOUS turns and historical context. "
            "Stored relational memories and facts on file contain older or general information.\n"
            "Do NOT confuse past visual/audio descriptions, previous conversation turns, or stored memories with current reality.\n"
            "Rely STRICTLY on the [Live Screen Perception] and [FINE-GRAINED PERCEPTION FACTS] sections above for what you currently see and hear. "
            "If the requested information (e.g., song title, visible text) is not present in the live snapshot, do NOT retrieve or guess it from memory or history. State clearly that you cannot perceive it right now.\n"
        )

    prompt = "<|im_start|>system\n" + system_content.strip() + "<|im_end|>\n"

    # Add history scaled by dynamic limits to avoid context overflow
    max_hist = limits["max_history"]
    stale_fallback_phrases = [
        "I can't see or hear your screen right now since screen sharing is inactive",
        "Hit 'Share Screen' in the dashboard whenever you're ready",
        "I can't hear your screen audio because screen sharing isn't active",
        "I can't read your screen because screen sharing is inactive",
        "I can't track changes because screen sharing is currently inactive"
    ]
    for msg in history[-max_hist:]:
        if msg.startswith("You: "):
            prompt += f"<|im_start|>user\n{msg[5:].strip()}<|im_end|>\n"
        elif msg.startswith("Vivy: "):
            content = msg[6:].strip()
            # Filter out stale canned perception fallbacks from past history
            if any(phrase.lower() in content.lower() for phrase in stale_fallback_phrases):
                continue
            prompt += f"<|im_start|>assistant\n{content}<|im_end|>\n"

    # Add current user turn
    prompt += f"<|im_start|>user\n{user.strip()}<|im_end|>\n"
    prompt += "<|im_start|>assistant\n"
    return prompt

# ===============================
# OUTPUT FILTER
# ===============================
# Fix #2 — Compiled pattern to strip <think>...</think> blocks and orphaned tags
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_TAG_RE = re.compile(r"</?think>", re.IGNORECASE)

# PART 2 — Robotic phrase blocklist. Any reply starting with these is regenerated.
_ROBOTIC_PHRASES = [
    "interesting", "i understand", "as an ai", "certainly",
    "that caught my attention", "thank you for sharing",
    "i appreciate that", "could you elaborate", "how may i",
    "that's interesting", "tell me more", "great question",
    "of course", "sure thing", "absolutely", "indeed",
    "hmm...", "hmm", "i'm here", "i am here", "i see",
    "let's see", "as a language model", "how can i help",
    "is there anything else",
    # Fix 4: Additional reasoning/robotic openers that leak through
    "okay,", "okay.", "okay!", "alright,", "alright.",
    "let me ", "so, ", "now, ", "well, let me", "well, i",
    "i need to", "i should", "i'll keep", "i must",
    "now i need", "so i should", "now let's",
    "the user", "user asked", "user is", "user wants",
    "my response", "my reply", "in this case", "in this conversation",
    "according to", "based on the", "given that",
    "you're a good sport", "you are a good sport", "what a sport",
    # Session 8: block virtual assistant prose
    "eager to help", "always here to help", "how can i assist", "anything else i can",
    # Phase 6: anti-cliché phrase blocklist
    "i'm definitely listening", "that's unexpected", "keep going",
    "that's fascinating", "your stomach speaks", "in the best kind of way",
    "always manage to catch me off guard", "making this way more interesting"
]

def _is_robotic(t, mem=None, user=""):
    """Return True if reply opens with a blocked robotic phrase."""
    tl = t.lower().lstrip()
    active_task = mem.get("active_task", "none") if mem else "none"
    
    blocked_phrases = _ROBOTIC_PHRASES
    
    # Define safe starters that should be allowed in tasks or when answering questions
    safe_prefixes = set()
    if active_task != "none":
        safe_prefixes.update([
            "okay,", "okay.", "okay!", "alright,", "alright.",
            "let me ", "so, ", "now, ", "well, let me", "well, i",
            "now i need", "so i should", "now let's"
        ])
    if active_task != "none" or (user and "?" in user):
        safe_prefixes.update([
            "absolutely", "of course", "ok", "okay"
            # Note: "sure thing" is intentionally excluded — it's always robotic regardless of task
        ])
        
    is_perc = is_perception_query_check(user) if user else False
    if is_perc:
        safe_prefixes.update([
            "i see", "i hear", "i can see", "i can hear", "i detect", "i'm seeing", "i'm hearing"
        ])
        
    if safe_prefixes:
        blocked_phrases = [p for p in _ROBOTIC_PHRASES if not any(p.startswith(sp) for sp in safe_prefixes)]
        
    return any(tl.startswith(p) for p in blocked_phrases)

# =====================================================
# PART 5 — RESPONSE INTELLIGENCE ENGINE (RIE)
# =====================================================
def get_previous_replies(history):
    replies = []
    if history:
        for turn in history:
            if turn.startswith("Vivy: "):
                replies.append(turn[6:].strip())
    return replies

def score_response_rie(reply, user, mem, categories, history=None, perception_state=None):
    """Evaluate candidate response against 8 quality metrics.
    Must average >= 8.5 and minimum score per check must be passed.
    Returns (average_score, is_valid) tuple."""
    t = reply.strip()
    if not t or (len(t.split()) < 2 and not any(ord(c) > 127 for c in t)):
        return 0.0, False
        
    # Truncation and Incompleteness Guard
    t_stripped = t.rstrip(":.— \t\n、，：〜")
    if t.endswith(":") or t.endswith("—") or t.endswith("-") or t.endswith(",") or t.endswith("、") or t.endswith("，") or t.endswith("：") or t.endswith("〜"):
        print("Response validation rejected candidate: Response ends with truncation characters.")
        return 0.0, False
    if t_stripped.lower().endswith("reads") or t_stripped.lower().endswith("reads:"):
        print("Response validation rejected candidate: Response ends with unfinished 'reads' phrase.")
        return 0.0, False
    # Fix 6: Whole-reply reasoning check — if the ENTIRE reply reads as reasoning, reject immediately.
    # This catches multi-sentence reasoning leaks where individual sentences pass but the whole is bad.
    if is_reasoning_sentence(t):
        return 0.0, False
    # Reject candidate if any sentence contains internal system reasoning
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', t) if s.strip()]
    if any(is_reasoning_sentence(s) for s in sentences):
        return 0.0, False
    if _is_robotic(t, mem, user):
        return 0.0, False
    # Anywhere-in-reply blocker: these phrases destroy immersion regardless of position
    _ANYWHERE_BLOCKED = [
        "i'm not a doctor", "i am not a doctor",
        "i'm not a medical", "i am not a medical",
        "consult a doctor", "consult a healthcare",
        "consult a professional", "seek professional medical",
        "i'm just an ai", "i am just an ai",
        "as an ai", "as a language model",
        "you have a way of making me", "i can't help but notice",
        "you're a good sport", "what a good sport", "good sport",
        "i'll bring you", "let me get you", "i'll get you", "i'll make you",
        "i'm bringing", "i'll bring a", "i can bring", "i will bring you",
        "i'll bring", "let me bring", "i'll grab",
        # Session 8: block virtual assistant prose anywhere in reply
        "eager to help", "always here to help", "how can i assist", "anything else i can",
        # Screenplay dramatic dialogue blockers (Movie Dialogue Syndrome)
        "asking the wrong question", "ask the wrong question", "you're asking the wrong",
        "i've been chasing you", "chasing you all along", "chasing you",
        "something about the way you say that", "about the way you say that", "wrong question"
    ]
    # Block these physical action delegation phrases only in casual companion mode
    active_task = mem.get("active_task", "none")
    ts = mem.get("task_state", {})
    if active_task != "cooking":
        _ANYWHERE_BLOCKED.extend([
            "you grab the", "you find the", "you get the",
            "grab the bread", "grab the cheese", "you look for", "you check the"
        ])
    t_lower_full = t.lower()
    if mem.get("emotional_beat_active"):
        leak_words = ["recipe", "ingredient", "cook", "burger", "pizza", "ramen", "pasta", "chicken", "food", 
                      "boil", "pan", "patty", "bun", "cheese", "bread", "onion", "skillet", "pantry", "fridge", "cupboard"]
        if any(w in t_lower_full for w in leak_words):
            print(f"Response validation rejected candidate: Cooking context leak detected during emotional beat: {t_lower_full}")
            return 0.0, False

    if any(blocked in t_lower_full for blocked in _ANYWHERE_BLOCKED):
        print(f"Response validation rejected candidate: Anywhere-blocked phrase detected")
        return 0.0, False
        
    # Only reject actual LLM system/thought tags to allow code brackets
    system_tags = ["<|im_start|>", "<|im_end|>", "<|endoftext|>", "<|user|>", "<|system|>", "<|assistant|>", "<think>", "</think>"]
    if any(tag in t for tag in system_tags):
        return 0.0, False
    if similarity(t.lower(), user.lower()) > 0.6:
        return 0.0, False

    # Visual/Audio Grounding & Perception Capability Contradiction Guard
    try:
        from perception.perception_manager import get_reader, log_capability_mismatch
        p_reader = get_reader()
        p_state_live = perception_state if isinstance(perception_state, dict) and perception_state else p_reader.load_state()
        
        cam_active = p_state_live.get("camera_active", False)
        face_det = p_state_live.get("face_detected", False) or (p_state_live.get("face_count", 0) > 0)
        screen_act = p_state_live.get("screen_sharing_active", False)
        
        t_lower = t.lower()
        
        # 1. Reject visual negation when camera is ON and face is detected
        if cam_active and face_det:
            negations = ["cannot see you", "can't see you", "don't see your face", "can't see your face", "unable to see you", "can't see any face"]
            if any(neg in t_lower for neg in negations):
                print(f"[Capability Guard] Rejected candidate: LLM denied seeing user while camera_active=True and face_detected=True. Reply: '{t}'")
                log_capability_mismatch("user_visible=True", "LLM claimed unable to see user", "score_response_rie", {"reply": t})
                return 0.0, False
                
        # 2. Reject visual claims when both camera and screen share are OFF
        if not cam_active and not screen_act:
            claims = ["i can see your face", "i see your face", "i can see you", "i see you looking", "i can see both your screen", "i can see your screen"]
            if any(claim in t_lower for claim in claims):
                print(f"[Capability Guard] Rejected candidate: LLM claimed visual perception while camera_active=False and screen_sharing_active=False. Reply: '{t}'")
                log_capability_mismatch("visual_input=False", "LLM claimed visual perception", "score_response_rie", {"reply": t})
                return 0.0, False

        # 3. Reject screen share contradictions
        if screen_act:
            if any(neg in t_lower for neg in ["cannot see your screen", "can't see your screen", "screen share is off", "screen is not shared"]):
                print(f"[Capability Guard] Rejected candidate: LLM denied screen access while screen_sharing_active=True. Reply: '{t}'")
                log_capability_mismatch("screen_sharing_active=True", "LLM claimed unable to see screen", "score_response_rie", {"reply": t})
                return 0.0, False

        if is_perception_query_check(user, perception_state):
            # Prefer passed perception_state if available and non-empty, otherwise read
            p_state = p_state_live
            user_lower = user.lower().strip()
            
            # A. Highlight check
            if any(w in user_lower for w in ["highlighted", "selected", "written", "selection"]):
                highlighted = p_state.get("highlighted_region_text", "").strip()
                if highlighted:
                    hl_words = [w for w in re.findall(r"\w+", highlighted.lower()) if len(w) > 2]
                    if hl_words:
                        match_count = sum(1 for w in hl_words if w in t_lower_full)
                        if match_count < max(1, len(hl_words) // 2):
                            print(f"Grounded Perception Validator: reply does not contain highlighted text '{highlighted}'. Rejecting.")
                            return 0.0, False
                            
            # B. Focused Window check
            if any(w in user_lower for w in ["app", "window", "program", "opened"]):
                win_title = p_state.get("active_window_title", "").strip()
                if win_title:
                    win_words = [w for w in re.findall(r"\w+", win_title.lower()) if len(w) > 2]
                    if win_words and not any(w in t_lower_full for w in win_words):
                        print(f"Grounded Perception Validator: reply does not mention active window '{win_title}'. Rejecting.")
                        return 0.0, False

            # C. Audio details check
            if any(w in user_lower for w in ["hear", "audio", "sound", "playing", "music", "song"]):
                # Ensure the response does NOT quote lyrics if no audio transcript is present
                transcript = p_state.get("screen_audio_transcript", "").strip()
                music_title = p_state.get("audio_music_title", "").strip()
                event_desc = p_state.get("audio_event_description", "").strip()
                
                # Check for lyrics quoting in the response if none in transcript
                if not transcript:
                    # Look for double or single quotes indicating lyrics quoting
                    quoted_phrases = re.findall(r'"([^"]+)"', t) + re.findall(r"'([^']+)'", t)
                    if music_title:
                        quoted_phrases = [q for q in quoted_phrases if q.lower() not in music_title.lower()]
                    # Reject if the response invents lyrics quotes
                    if any(len(qp.split()) >= 2 for qp in quoted_phrases):
                        print("Grounded Perception Validator: reply quotes lyrics or text but no audio transcript exists. Rejecting.")
                        return 0.0, False
                        
                # Check for hallucinated technical/vibe adjectives if not grounded in event_desc
                ungrounded_vibes = ["haunting vocals", "pounding beats", "thumping", "electric vibe", "stuck in that loop"]
                if any(vibe in t_lower_full for vibe in ungrounded_vibes):
                    # Only allow if those exact phrases are in event_desc
                    if not any(vibe in event_desc.lower() for vibe in ungrounded_vibes):
                        print("Grounded Perception Validator: reply contains ungrounded vibe/adjective detail. Rejecting.")
                        return 0.0, False
    except Exception as g_err:
        print(f"Grounded Perception Validator exception (non-fatal): {g_err}")

    # Topic Consistency & Cross-Contamination Guard
    if active_task == "cooking":
        query = ts.get("query", "").lower()
        if query:
            # If query is pizza, and response mentions noodles/ramen/pasta sheets/lasagna
            if "pizza" in query and any(w in t_lower_full for w in ["noodle", "ramen", "pasta sheet", "lasagna"]):
                print("Topic Consistency Validator: pizza query contains noodle/pasta terms. Rejecting.")
                return 0.0, False
            # If query is ramen, and response mentions pizza crust/dough/cheese/lasagna
            if "ramen" in query and any(w in t_lower_full for w in ["pizza", "dough", "crust", "lasagna"]):
                print("Topic Consistency Validator: ramen query contains pizza terms. Rejecting.")
                return 0.0, False
            # If query is pasta, and response mentions ramen/broth/yeast/pizza crust
            if "pasta" in query and any(w in t_lower_full for w in ["ramen", "yeast", "crust"]):
                print("Topic Consistency Validator: pasta query contains ramen/pizza terms. Rejecting.")
                return 0.0, False

    # Task Consistency & Completion Guards (Session 8)
    active_task = mem.get("active_task", "none")
    strategy_plan = mem.get("strategy_plan", {})
    strategy = strategy_plan.get("strategy", "medium")
    
    if active_task == "cooking" and ("continuation" in categories or "recipe" in categories or "food_need" in categories):
        # Fix 9g: loosen checks for clarification/empty-handed phases or initial conversational turn
        is_clarification_or_empty = ts.get("needs_clarification") or ts.get("empty_handed")
        # If skip_prep is False and strategy is not tutorial, it's just a friendly prep/ask question, don't reject
        is_prep_turn = not ts.get("skip_prep") and strategy != "tutorial"
        if not is_clarification_or_empty and not is_prep_turn:
            food_terms = ["recipe", "ingredient", "cook", "boil", "water", "noodle", "ramen", "pizza", "pan", "heat", "toastie", "cheese", "bread", "craving", "craved", "eat", "food", "kitchen", "cupboard", "fridge", "pantry"]
            try:
                from config.config_manager import get_config_manager
                cfg_terms = get_config_manager().get("multilingual_engine", {}).get("multilingual_task_terms", {}).get("cooking", [])
                if cfg_terms:
                    food_terms.extend([term.lower() for term in cfg_terms])
            except Exception:
                pass
            task_query = ts.get("query", "").lower()
            if task_query:
                food_terms.extend(task_query.split())
            if not any(term in t_lower_full for term in food_terms):
                print(f"Response validation rejected candidate: Active cooking task but no food/recipe terms present.")
                return 0.0, False
            
            # If in tutorial mode (meaning we are delivering the recipe), ensure it is not truncated or empty
            if strategy == "tutorial" or ts.get("skip_prep"):
                # 1. Must be reasonably long for a full recipe (multilingual character aware)
                if len(t.split()) < 25 and len(t) < 80:
                    print("Response validation rejected candidate: Recipe tutorial is too short.")
                    return 0.0, False
                # 2. Must not end in trailing colons, dashes or commas (signals truncation)
                if t.endswith(":") or t.endswith("—") or t.endswith(","):
                    print("Response validation rejected candidate: Recipe tutorial is truncated/incomplete.")
                    return 0.0, False
                # 3. Must contain some step/list formatting (numbers or bullet points)
                has_list_formatting = any(marker in t for marker in ["1.", "2.", "•", "-", "*"])
                if not has_list_formatting:
                    print("Response validation rejected candidate: Recipe tutorial lacks list/step formatting.")
                    return 0.0, False
    # Sentence-level echo blocker: reject replies that paraphrase the user's message
    user_stripped = user.lower().strip("?!.,'")
    reply_sentences = [s.strip().lower().strip("?!.,'") for s in re.split(r'(?<=[.!?])\s+', t) if s.strip()]
    highlighted = ""
    if isinstance(perception_state, dict):
        highlighted = perception_state.get("highlighted_region_text", "").lower().strip("?!.,'\" ")
    for rs in reply_sentences:
        if len(rs.split()) >= 3 and similarity(rs, user_stripped) > 0.55:
            # If the user is asking about highlighted/selected text, and the rs matches the highlighted text, allow it!
            if highlighted and (similarity(rs, highlighted) > 0.85 or highlighted in rs):
                continue
            print(f"Response validation rejected: sentence-level echo detected ('{rs}')")
            return 0.0, False
        
    # Response Diversity Engine check (Volume 6)
    if history:
        previous = get_previous_replies(history)
        for prev_reply in previous[-5:]:
            # Check whole-reply similarity
            if similarity(t.lower(), prev_reply.lower()) > 0.70:
                print(f"Response validation rejected candidate: Semantic similarity too high to previous reply '{prev_reply}'")
                return 0.0, False
                
            # Check sentence-level similarity, substring matches, and Jaccard word set overlaps
            new_sentences = [s.strip().lower().strip(".,!?") for s in re.split(r'(?<=[.!?])\s+', t) if s.strip()]
            prev_sentences = [s.strip().lower().strip(".,!?") for s in re.split(r'(?<=[.!?])\s+', prev_reply) if s.strip()]
            for ns in new_sentences:
                ns_words = ns.split()
                if len(ns_words) < 3:
                    continue
                # Substring check
                if ns in prev_reply.lower() or prev_reply.lower() in ns:
                    print(f"Response validation rejected candidate: Phrase substring overlap detected ('{ns}')")
                    return 0.0, False
                    
                for ps in prev_sentences:
                    ps_words = ps.split()
                    if len(ps_words) < 3:
                        continue
                    # Jaccard overlap check
                    overlap = set(ns_words).intersection(set(ps_words))
                    union = set(ns_words).union(set(ps_words))
                    jaccard = len(overlap) / len(union) if union else 0.0
                    
                    if similarity(ns, ps) > 0.75 or jaccard > 0.60:
                        print(f"Response validation rejected candidate: Phrase similarity too high ('{ns}' vs '{ps}', similarity={similarity(ns, ps):.2f}, jaccard={jaccard:.2f})")
                        return 0.0, False
        
    reply_lower = t.lower()
    
    # Memory claims validation (no hallucination check)
    memory_claims = [
        "remember when we", "last time we", "as we discussed", "you mentioned before", "we talked about last time",
        # Session 4 additions: catch fabricated episodic memories
        "remember that", "remember the", "we talked about yesterday", "yesterday we", "we were at",
        "that time at the", "at the cafe", "at the caf", "that pizza we", "that funny moment",
        "we mentioned", "you told me yesterday", "earlier we", "the other day we"
    ]
    if any(claim in reply_lower for claim in memory_claims):
        has_matching_memory = False
        ranked_mem = rank_memories(user, mem)
        facts = mem.get("long_term_facts", {})
        if ranked_mem and str(ranked_mem).lower() in reply_lower:
            has_matching_memory = True
        else:
            for val in facts.values():
                if str(val).lower() in reply_lower:
                    has_matching_memory = True
                    break
        if not has_matching_memory:
            print("Response validation rejected candidate: Hallucinated memory claim.")
            return 0.0, False
            
    # Emotional overshooting check
    rel_score = mem.get("relationship", {}).get("score", 30)
    if rel_score < 50:
        exaggerated_terms = [
            "waiting forever", "been waiting for you", "best thing ever", 
            "only one for me", "can't live without", "always thinking of you", 
            "love you so much", "my love", "sweetheart", "darling"
        ]
        if any(term in reply_lower for term in exaggerated_terms):
            print("Response validation rejected candidate: Low-trust emotional overshooting.")
            return 0.0, False
        
    # Metric 1: Naturalness (starts capital or regional script, ends with punctuation)
    naturalness = 10.0 if (t[0].isupper() or ord(t[0]) > 127) and t[-1] in [".", "!", "?", "。", "！", "？", "।"] else 7.0
    
    # Metric 2: Warmth (persona keywords)
    warmth = 8.5
    warm_indicators = ["smile", "blush", "cute", "warm", "hey", "back", "tease", "trouble", "sweet", "fun", "blushing", "giggle"]
    if any(w in t.lower() for w in warm_indicators):
        warmth = 10.0
        
    # Metric 3: Context awareness (word overlap)
    context = 8.5
    user_words = set(extract_keywords(user))
    reply_words = set(t.lower().split())
    if user_words.intersection(reply_words):
        context = 10.0
        
    # Metric 4: Continuation (hooks / questions)
    continuation = 8.0
    if "?" in t or any(w in t.lower() for w in ["about you", "what about", "your turn", "you think"]):
        continuation = 10.0
        
    # Metric 5: Flow
    flow = 9.0
    
    # Metric 6: Emotion vector matching
    emotion = 9.0
    
    # Metric 7: Memory usage
    memory = 8.5
    facts = mem.get("long_term_facts", {})
    if any(str(val).lower() in t.lower() for val in facts.values() if len(str(val)) > 3):
        memory = 10.0
        
    # Metric 8: Personality consistency
    personality = 9.5
    
    avg = (naturalness + warmth + context + flow + continuation + emotion + memory + personality) / 8.0
    is_valid = (avg >= 8.5) and (len(t.split()) >= 2 or any(ord(c) > 127 for c in t))
    return avg, is_valid

# =====================================================
# PART 6 — INTELLIGENT CONTEXT & SUMMARY ENGINES
# =====================================================
def update_topics_pipeline(user, mem):
    """Detect topic switches, rank active topics, and manage restoration stack (PART 7)."""
    # Active Task Override: lock topic to the current task to prevent drift during multi-turn flows
    active_task = mem.get("active_task", "none")
    if active_task == "cooking":
        mem["current_topic"] = "recipes/cooking"
        mem["topic_confidence"] = 0.95
        return
    elif active_task == "health":
        mem["current_topic"] = "health"
        mem["topic_confidence"] = 0.95
        return

    l = user.lower()

    if mem.get("emotional_beat_active"):
        relationship_keywords = ["hug", "cuddle", "kiss", "love", "like me", "miss", "angry", "ask u", "ask you"]
        if any(w in l for w in relationship_keywords):
            mem["current_topic"] = "relationship/flirting"
        else:
            mem["current_topic"] = "general"
        mem["topic_confidence"] = 0.95
        return
    
    technical_words = ["code", "python", "bug", "error", "api", "function", "program", "llama", "qwen", "git", "database"]
    anime_words = ["anime", "manga", "manhwa", "watch", "read", "show", "series"]
    food_words = ["hungry", "food", "eat", "pizza", "lunch", "dinner", "burger", "cook", "recipe", "ingredients"]
    flirting_words = ["cute", "love", "like you", "miss", "blush", "charming", "crush", "flirt"]
    
    new_topic = "general"
    confidence = 0.7
    
    if any(w in l for w in technical_words):
        new_topic = "programming/technical"
        confidence = 0.95
    elif any(w in l for w in food_words):
        new_topic = "recipes/cooking"
        confidence = 0.95
    elif any(w in l for w in anime_words):
        new_topic = "anime/manga"
        confidence = 0.95
    elif any(w in l for w in flirting_words):
        new_topic = "relationship/flirting"
        confidence = 0.90
    elif any(w in l for w in ["recommend", "suggest", "best movie", "best book", "best game", "good anime"]):
        new_topic = "recommendations"
        confidence = 0.90
    elif any(w in l for w in ["why is", "how does", "what is the capital", "population of", "who wrote", "what is the speed"]):
        new_topic = "general knowledge"
        confidence = 0.90
        
    old_topic = mem.get("current_topic")
    if new_topic != old_topic:
        # Pivot detection: store active topic in interrupted stack ONLY if we are switching to a new specific topic
        if old_topic and old_topic != "general" and new_topic != "general":
            if old_topic not in mem.get("interrupted_topics", []):
                mem.setdefault("interrupted_topics", []).append(old_topic)
                mem["interrupted_topics"] = mem["interrupted_topics"][-3:]
                print(f"Interrupted topic stored: {old_topic}")
        
        # If transitioning to general, immediately check if we can restore a previous topic
        if new_topic == "general" and mem.get("interrupted_topics"):
            restored = mem["interrupted_topics"].pop()
            mem["current_topic"] = restored
            mem["topic_confidence"] = 0.8
            print(f"Restored interrupted topic: {restored}")
        else:
            mem["current_topic"] = new_topic
            mem["topic_confidence"] = confidence
    else:
        # Boost confidence on reinforcement
        mem["topic_confidence"] = min(1.0, mem.get("topic_confidence", 0.7) + 0.05)

# =====================================================
# PART 7 — PLANNER SUBSYSTEM
# =====================================================
def planner_subsystem(user, mem, categories):
    """Analyze user intent to plan conversation goals and expected tone."""
    # 1. Determine Dynamic Conversation Goal
    if "health" in categories:
        goal = "health companion / caring presence"
    elif "food_need" in categories:
        goal = "food / recipe helper"
    elif ("affirmative" in categories or "continuation" in categories) and mem.get("current_topic") == "recipes/cooking":
        goal = "recipe task advancement"
    elif "recipe" in categories:
        goal = "recipe assistance"
    elif "recommendation" in categories:
        goal = "recommendations"
    elif "knowledge" in categories:
        goal = "information retrieval"
    elif "technical" in categories:
        goal = "technical assistance"
    elif "gratitude" in categories:
        goal = "emotional acknowledgement"
    elif "compliment" in categories or "flirting" in categories:
        goal = "relational bonding"
    elif "joke" in categories:
        goal = "socializing / humor"
    else:
        goal = "socializing / casual chat"
        
    mem["conversation_goal"] = goal
    
    # 2. Plan Directives
    states = mem.get("temporary_states", {})
    need_humor = ("joke" in categories) or ("hungry" in states) or ("tired" in states)
    
    mem["planner_state"] = {
        "primary_goal": goal,
        "secondary_goal": "relationship growth" if goal == "relational bonding" else "friendly engagement",
        "need_humor": need_humor
    }

def rank_memories(user, mem):
    """Score and prioritize long-term memories based on importance, similarity, and relationship score.
    Returns the top single memory value, filtering out duplicates."""
    facts = mem.get("long_term_facts", {})
    if not facts:
        return ""
        
    scored = []
    rel_score = mem.get("relationship", {}).get("score", 30)
    
    for key, val in facts.items():
        if key == "name":
            continue
            
        # 1. Base Importance Score
        importance = 5.0
        if "like" in key or "dislike" in key:
            importance = 7.0
        elif "occupation" in key:
            importance = 8.0
            
        # 2. Similarity Score
        sim = similarity(str(val).lower(), user.lower()) * 10.0
        
        # 3. Relationship Multiplier
        rel_boost = rel_score / 200.0  # up to +0.5
        
        total_score = importance + sim + rel_boost
        scored.append((total_score, val))
        
    if not scored:
        return ""
        
    # Sort by total score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    # Return the value of the top ranked memory
    return scored[0][1]

def update_summary_incremental(mem, removed_turns):
    """Lightweight incremental LLM-based dialogue compressor."""
    if not removed_turns:
        return
    turns_text = "\n".join(removed_turns)
    prompt = (
        "<|im_start|>system\n"
        "You are an assistant updating a running summary of a conversation.\n"
        f"Current Summary: {mem.get('summary', '')}\n"
        "New turns:\n"
        f"{turns_text}\n"
        "Summarize the context, user facts, and tasks in one short sentence. Do not mention being an AI.\n"
        "<|im_end|>\n"
        "<|im_start|>assistant\n"
    )
    try:
        out = llm(prompt, max_tokens=50, temperature=0.3, stop=["<|im_end|>"])
        new_sum = out["choices"][0]["text"].strip()
        # Clean any assistant prefix
        new_sum = re.sub(r'^(Summary|Assistant|Vivy):\s*', '', new_sum, flags=re.IGNORECASE)
        if new_sum:
            mem["summary"] = new_sum
            print(f"Summary engine updated: {new_sum}")
    except Exception as e:
        print(f"Summary engine error: {e}")

def update_questions_promises(user, reply, mem):
    """Track unanswered questions and Vivy's promises."""
    # 1. Track User Questions
    if "?" in user:
        clean_q = user.strip()
        if clean_q not in mem["open_questions"]:
            mem["open_questions"].append(clean_q)
            mem["open_questions"] = mem["open_questions"][-3:]
            
    # Resolve user question once Vivy replies
    if mem["open_questions"] and len(reply) > 10:
        mem["open_questions"].pop(0)
        
    # 2. Track Vivy's Promises
    promise_indicators = ["i will", "i promise", "i'll remember", "remind you", "i'll make sure"]
    reply_lower = reply.lower()
    if any(ind in reply_lower for ind in promise_indicators):
        sentences = re.split(r'[.!?]', reply)
        for s in sentences:
            s_clean = s.strip()
            if any(ind in s_clean.lower() for ind in promise_indicators):
                if s_clean not in mem["promises"]:
                    mem["promises"].append(s_clean)
                    mem["promises"] = mem["promises"][-3:]
                    print(f"Recorded promise: '{s_clean}'")

def is_reasoning_sentence(s):
    """Detect if a sentence is part of Vivy's system/meta-level reasoning.
    Fix 2: Massively expanded to catch all known Qwen3 reasoning leak patterns.
    Preserves all original patterns and adds comprehensive new ones."""
    sl = s.lower().strip()
    
    # --- Original patterns (preserved exactly) ---
    meta_verbs = r"(answer|reply|tease|flirt|blush|be|greet|show|acknowledge|respond|say|ask|remain|tell|write|react|act|do)"
    original_patterns = [
        rf"^i (should|decided|think i should|will|need to|must|want to|ought to|am going to|let me|shall|should not)\s+{meta_verbs}",
        r"^i checked\s+(the\s+)?(history|memory|conversation|log)",
        r"^the user\s+(is|asked|wants|said|wishes|names|tells|profile)",
        r"^this conversation",
        r"^my reasoning",
        r"^vivy should",
        r"^assistant should",
        r"\b(internal thoughts|system prompt|user name|active tone|directive)\b"
    ]
    if any(re.search(p, sl) for p in original_patterns):
        return True
    if "i decided to" in sl or "i think i should" in sl or "i will answer" in sl or "my reasoning" in sl or "i checked the history" in sl:
        return True
    
    # --- Fix 2: Extended patterns for Qwen3 reasoning leaks ---
    
    # Pattern Group A: "Okay, ..." reasoning starters
    # Catches: "Okay, the user asked...", "Okay, I need to...", "Okay, let me..."
    okay_reasoning_re = re.compile(
        r"^okay[,!.]?\s+(the user|i need|let me|i should|i'll|i have to|i must|so|now|this means|here)",
        re.IGNORECASE
    )
    if okay_reasoning_re.match(sl):
        return True
    
    # Pattern Group B: "Let me ..." meta-action starters  
    # Catches: "Let me check...", "Let me think...", "Let me consider...", "Let me re-read..."
    let_me_re = re.compile(
        r"^let me\s+(check|think|consider|re-read|look|review|see|re-check|figure|make sure|respond|craft|write|keep|ensure)",
        re.IGNORECASE
    )
    if let_me_re.match(sl):
        return True
    
    # Pattern Group C: "I need to keep..." / "I need to respond..."
    # Catches: "I need to keep replies brief", "I need to respond in a very short way"
    i_need_re = re.compile(
        r"^i need to (keep|make|ensure|follow|maintain|respond|reply|check|avoid|be|stay|use|generate|craft)",
        re.IGNORECASE
    )
    if i_need_re.match(sl):
        return True
    
    # Pattern Group D: "Now I need..." / "So I should..." / "Now let me..."
    now_so_re = re.compile(
        r"^(now|so)\s+(i need|i should|i'll|i must|let me|i can|i want|the user)",
        re.IGNORECASE
    )
    if now_so_re.match(sl):
        return True
    
    # Pattern Group E: User-referencing meta-commentary
    # Catches: "The user is Satyajeet", "The user started with a greeting", "They might be feeling lonely"
    user_ref_re = re.compile(
        r"^(the user|user|satyajeet|they) (is|are|just|was|has|asked|said|started|seems|appears|wants|needs|keeps|told|might|may|can|will|must|should)",
        re.IGNORECASE
    )
    if user_ref_re.match(sl):
        return True
    
    # Pattern Group F: Guideline/rule referencing
    # Catches: "I need to follow the guidelines", "According to the rules..."
    guideline_re = re.compile(
        r"(follow|check|according to|based on|per|as per)\s+(the\s+)?(guideline|rule|instruction|directive|system|prompt|persona|context|history|memory)",
        re.IGNORECASE
    )
    if guideline_re.search(sl):
        return True

    # Pattern Group G: Self-referential planning statements
    # Catches: "I'll keep it friendly", "I should respond in a way that's..."
    self_plan_re = re.compile(
        r"^i('ll| will| should| must| need to| am going to)\s+(keep|make|ensure|stay|respond|reply|craft|write|avoid|be|remain|use|think|check|follow|acknowledge)",
        re.IGNORECASE
    )
    if self_plan_re.match(sl):
        return True
    
    # Pattern Group H: Direct substring fast-checks for common recurring leaks
    leak_substrings = [
        "the guidelines", "the rules", "the persona", "the system",
        "my guidelines", "my instructions", "my response should",
        "keep replies brief", "keep it brief", "keep it short",
        "the conversation has started", "conversation started with",
        "let me check", "let me think", "let me see",
        "i'm checking", "i am checking", "need to follow",
        "need to respond", "need to reply", "need to keep",
        "in a very short", "10-15 words", "1-3 sentences",
        "the tone should", "tone is neutral", "tone should be",
        "a bit of a playful", "respond in a way", "a way that's",
        "asked about", "asking if i", "asking me",
        "i'm definitely listening", "that's unexpected", "keep going",
        "interesting", "that's fascinating", "your stomach speaks",
        "in the best kind of way", "always manage to catch me off guard",
        "making this way more interesting",
        "since i'm supposed to be", "since i am supposed to be",
        "since i'm supposed", "supposed to be a companion",
        "okay, the user just said", "the user just said",
        "they might be feeling lonely", "looking for company",
        "i should respond with warmth", "respond with warmth and empathy",
        "how to approach this", "let me think about how",
        "this sounds like a developer log", "developer log",
        "as a companion, i should", "as a friend, i should",
        "user just asked", "user keeps saying", "user keeps asking",
    ]
    if any(sub in sl for sub in leak_substrings):
        return True
        
    return False

def clean(text, user, mem):
    t = text.strip()
    # Strip thoughts if the prompt pre-filled <think> but the output only generated </think>
    if "</think>" in t:
        t = t.split("</think>")[-1].strip()
    # Fix #2 — Strip <think>...</think> blocks and any orphaned <think> tags
    t = _THINK_BLOCK_RE.sub("", t).strip()
    t = _THINK_TAG_RE.sub("", t).strip()
    # Fix #3 — Remove LLM role-play prefixes BEFORE splitting lines
    t = re.sub(r'^(Vivy|You|User|Assistant|Vivy AI|Assistant AI):\s*', '', t, flags=re.IGNORECASE)
    if mem.get("name"):
        t = re.sub(rf'^{re.escape(mem["name"])}:\s*', '', t, flags=re.IGNORECASE)
        
    # Strip prompt/system leakage tags
    t = re.sub(r'\[(?:directive|state|active topic|interrupted|conversation summary|goal planner|unresolved|your active|humor engine|reply limit|reply length|active narrative)[^\]]*\]', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\((?:directive|state|active topic|interrupted|conversation summary|goal planner|unresolved|your active|humor engine|reply limit|reply length|active narrative)[^\)]*\)', '', t, flags=re.IGNORECASE)
    
    # Strip markdown bold (**text**) and italic (*text*) formatting — LLM sometimes uses markdown
    # that shows as literal asterisks in terminal/UI. Strip cleanly.
    t = re.sub(r'\*\*([^*]+)\*\*', r'\1', t)  # **bold** → plain
    t = re.sub(r'\*([^*]+)\*', r'\1', t)        # *italic* → plain
    t = re.sub(r'__([^_]+)__', r'\1', t)         # __bold__ → plain
    t = re.sub(r'_([^_]+)_', r'\1', t)           # _italic_ → plain

    # Strip standalone or bracketed/parenthesized/asterisked emotion labels
    t = re.sub(r'[\(\[\*\:](?:joy|surprise|sad|anger|fear|disgust|neutral|happy|cheerful|playful|affectionate|flustered|relaxed|curious|confident|warm|excited|mood|emotions)[\)\]\*\:]', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(JOY|SURPRISE|SAD|ANGER|FEAR|DISGUST|NEUTRAL|HAPPY|CHEERFUL|PLAYFUL|AFFECTIONATE|FLUSTERED|RELAXED|CURIOUS|CONFIDENT|WARM|EXCITED)\b', '', t)

    # For recipe/tutorial content (multi-line), preserve full text. For companion chat, take first line only.
    lines = [l.strip() for l in t.split("\n") if l.strip()]
    strategy_plan_check = mem.get("strategy_plan", {})
    strategy_check = strategy_plan_check.get("strategy", "medium")
    active_task_check = mem.get("active_task", "none")
    # Upgrade: If the user is requesting a detailed visual/perception description, or if
    # the response strategy is "long" or "tutorial" or it is a perception query, preserve all lines!
    is_detailed_perception = (
        ("screen" in classify_message(user) or "audio_query" in classify_message(user)) and
        any(w in user.lower() for w in ["describe", "everything", "what changed", "detail", "breakdown", "all", "what happened", "history"])
    )
    if strategy_check in ("tutorial", "long", "perception", "perception_detailed") or active_task_check in ("cooking", "health") or is_detailed_perception:
        # Preserve all lines for structured responses
        t = "\n".join(lines) if lines else ""
    else:
        # Preserve all sentences/lines naturally for companion chat
        t = " ".join(lines) if lines else ""
    # Fix #3 — Also strip if name prefix re-appears
    if mem.get("name"):
        t = re.sub(rf'^{re.escape(mem["name"])}:\s*', '', t, flags=re.IGNORECASE)

    if not t:
        return ""
        
    # Session 7: Strip repetitive chatbot prefix finger-prints
    chatbot_starters = [
        "oh, ", "oh... ", "oh— ", "oh ",
        "hmm, ", "hmm... ", "hmm— ", "hmm ",
        "wait, ", "wait... ", "wait— ", "wait ",
        "really, ", "really... ", "really— ", "really ",
        "well, ", "well... ", "well— ", "well ",
        "okay, ", "okay... ", "okay— ", "okay "
    ]
    tl = t.lower()
    for s in chatbot_starters:
        if tl.startswith(s):
            t = t[len(s):].strip()
            if t:
                t = t[0].upper() + t[1:]
            break

    # Session 7: End-of-reply question stripping if ask_question is False
    strategy_plan = mem.get("strategy_plan", {})
    ask_question = strategy_plan.get("ask_question", True)
    if not ask_question and "?" in t:
        # Split carefully: for tutorial mode, split by lines first to avoid breaking recipe structure
        strategy_aq = strategy_plan.get("strategy", "medium")
        active_task_aq = mem.get("active_task", "none")
        if strategy_aq == "tutorial" or active_task_aq in ("cooking", "health"):
            aq_lines = t.split("\n")
            if aq_lines and aq_lines[-1].strip().endswith("?"):
                aq_lines = aq_lines[:-1]
                t = "\n".join(aq_lines).strip()
        else:
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', t) if s.strip()]
            if len(sentences) >= 2 and sentences[-1].endswith("?"):
                sentences.pop()
                t = " ".join(sentences).strip()

    if not t:
        return ""
    
    # Fix 3: Whole-reply reasoning guard — before per-sentence filtering,
    # check if the ENTIRE reply text is a reasoning monologue.
    if is_reasoning_sentence(t):
        return ""

    # For tutorial/structured content: filter reasoning line-by-line, preserve newlines.
    # For companion chat: filter sentence-by-sentence, join with spaces.
    strategy_plan_f = mem.get("strategy_plan", {})
    strategy_f = strategy_plan_f.get("strategy", "medium")
    active_task_f = mem.get("active_task", "none")
    is_tutorial_mode = strategy_f == "tutorial" or active_task_f in ("cooking", "health")

    if is_tutorial_mode:
        # For recipes/health: preserve line structure, filter only reasoning lines
        t_lines = t.split("\n")
        filtered_lines = [ln for ln in t_lines if not is_reasoning_sentence(ln.strip()) or not ln.strip()]
        t = "\n".join(filtered_lines).strip()
    else:
        # For companion chat: split into sentences and filter reasoning
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', t) if s.strip()]
        filtered_sentences = [s for s in sentences if not is_reasoning_sentence(s)]
        t = " ".join(filtered_sentences).strip()

    if not t:
        return ""
        
    # PART 7 — Safety Manager: check for prompt injection or leakage patterns
    tl = t.lower()
    leak_indicators = ["[state:", "[directive:", "<|im", "system", "your current emotional"]
    if any(ind in tl for ind in leak_indicators):
        print(f"Safety Manager blocked prompt leakage candidate: '{t}'")
        return ""

    # PART 3 — Basic length and tag safety validation (multilingual script aware)
    if len(t.split()) < 2 and not any(ord(c) > 127 for c in t):  # Too short for English words
        return ""
        
    # Only reject actual LLM system/thought tags to allow code brackets
    system_tags = ["<|im_start|>", "<|im_end|>", "<|endoftext|>", "<|user|>", "<|system|>", "<|assistant|>", "<think>", "</think>"]
    if any(tag in t for tag in system_tags):
        return ""
    # PART 2 — Robotic phrase filter
    if _is_robotic(t, mem, user):
        return ""
    if similarity(t.lower(), user.lower()) > 0.6:
        return ""
    # Guard against last_reply being a think-tag artifact
    last = _THINK_TAG_RE.sub("", mem.get("last_reply", "")).strip()
    if last and similarity(t.lower(), last.lower()) > 0.7:
        return ""
    # PART 2 — Reply opening repetition filter
    if _opening_is_repeated(t, mem):
        return ""
    return t

def generate_followup_question(user, reply, mem, categories):
    """
    Phase 7 — Follow-Up Question Engine.
    Appends a natural context-advancing follow-up question if appropriate
    without jumping topics or starting over.
    """
    if not reply or "?" in reply:
        return reply

    topic = mem.get("current_topic", "general")
    if topic == "recipes" or "recipe" in categories:
        questions = [
            "Would you like me to walk you through the preparation steps?",
            "Do you have all the ingredients ready, or should we substitute anything?",
            "Want me to check another variation of this dish for you?"
        ]
    elif topic == "code" or "technical" in categories:
        questions = [
            "Would you like me to test or refine a specific part of this logic?",
            "Do you want to step through the implementation together?"
        ]
    elif topic == "health" or "health" in categories:
        questions = [
            "How long have you been feeling this way?",
            "Is there anything else feeling off right now?"
        ]
    else:
        questions = [
            "How do you feel about that?",
            "What do you think?",
            "How are things on your end right now?"
        ]
    import random
    q = random.choice(questions)
    return f"{reply} {q}"

# ===============================
# RUN
# ===============================
# Fix 5 (upgraded): Context-sensitive fallback pools.
# Selected based on director_state mode — never random across all contexts.
_FALLBACK_REPLIES = [
    "I'm right here with you. Tell me a little more about what's on your mind.",
    "I'm listening. How have things been going for you today?",
    "I hear you. What else has been on your mind?",
    "That sounds interesting—tell me what you're feeling about it.",
    "I appreciate you sharing that with me. I'm listening.",
    "I'm definitely attentive. How do you see things developing?",
    "That caught my attention. Tell me a bit more.",
    "I'm enjoying our conversation. What would you like to explore next?",
]

# Gratitude-specific fallbacks — warm acknowledgement, not topic-change curiosity
_FALLBACK_GRATITUDE = [
    "Always.",
    "Of course.",
    "You don't have to thank me.",
    "Just promise me you'll take care of yourself.",
    "Any time. Really.",
    "I'd feel better knowing you're actually looking after yourself.",
]

# Health-specific fallbacks — caring, grounded, not topic-change
_FALLBACK_HEALTH = [
    "I'm right here. Just tell me how you're feeling.",
    "Don't push through this. You need to rest.",
    "I wish I could make this easier for you.",
    "Even small sips of water help. Please try.",
    "I'm worried about you. How bad is it right now?",
]

# Cooking/recipe specific fallbacks — warm and natural, not chatbot-ish
_FALLBACK_RECIPE = [
    "Good choice. Warm and quick. What do you have to work with?",
    "That sounds good. Do you have the basic ingredients handy?",
    "Nice. Want me to walk you through it step by step?",
    "Let's make it. Got your ingredients ready?"
]

# Food need (hunger) fallbacks — playful, warm, natural companion tone
_FALLBACK_FOOD_NEED = [
    "Then that's officially today's first problem to solve. What are you in the mood for?",
    "Your stomach speaks and I listen. What are we feeling like today?",
    "Already? Tell me what you're craving and we'll figure it out.",
    "Good timing. What sounds good right now?"
]


def get_semantic_scene_understanding(perception_state) -> str:
    if not perception_state:
        return "I can't see your screen right now."
        
    app = perception_state.get("current_app_type", perception_state.get("app_type", "unknown"))
    win_title = perception_state.get("active_window_title", "")
    ocr_text = perception_state.get("last_ocr_text", perception_state.get("ocr_text", "")).strip()
    ocr_lower = ocr_text.lower()
    ocr_conf = perception_state.get("ocr_confidence", 1.0)
    
    # Heuristics for visual cues from state
    brightness = perception_state.get("brightness", 50.0)
    is_dark = brightness < 40 or "dark" in app.lower() or "dark" in win_title.lower()
    mode = "dark theme" if is_dark else "light theme"
    
    # Try to extract sidebar details from scene_layout if available
    layout = perception_state.get("scene_layout", {})
    has_sidebar = False
    if layout and isinstance(layout, dict):
        has_sidebar = any(z.get("name") == "sidebar" or "sidebar" in z.get("name", "").lower() for z in layout.get("zones", []))
    
    # Fallback to general checks if no layout zone
    if not has_sidebar:
        has_sidebar = perception_state.get("has_sidebar", False) or "sidebar" in ocr_lower
        
    density = perception_state.get("content_density", "moderate content")
    if not density or density == "moderate content":
        # Guess based on OCR length
        if len(ocr_text) > 400:
            density = "dense layout with text"
        elif len(ocr_text) > 100:
            density = "moderate layout"
        else:
            density = "mostly visual or sparse content"

    layout_desc = f"a {mode}"
    if has_sidebar:
        layout_desc += " with a sidebar panel"
    if density:
        layout_desc += f", showing a {density}"

    # 1. YouTube
    if "youtube" in app.lower() or "youtube" in win_title.lower() or "youtube" in ocr_lower:
        video_title = ""
        if "playing '" in app:
            import re
            m = re.search(r"playing '([^']+)'", app)
            if m:
                video_title = m.group(1)
        if not video_title and " - " in win_title:
            candidate = win_title.split(" - ")[0].strip()
            if not any(x in candidate.lower() for x in ("vivy ai", "localhost", "127.0.0.1", "dashboard")):
                video_title = candidate
        if not video_title:
            for line in ocr_text.split("\n"):
                if any(k in line.lower() for k in ["nightcore", "official video", "music video", "lyrics", " - "]) and len(line) < 120:
                    video_title = line.strip()
                    break
        
        clarity_note = ""
        if ocr_conf < 0.70 and ocr_text:
            clarity_note = " (some details are a bit blurry)"
            
        if video_title:
            return f"a browser window playing a YouTube video titled \"{video_title}\" in {mode}. The interface shows the main video player and control bar, with recommendation columns and a sidebar of recommendations{clarity_note}."
        return f"a web browser window open to YouTube in {mode}, browsing videos{clarity_note}."

    # 2. Manga/Manhwa
    if any(k in ocr_lower for k in ["chapter", "manga", "manhwa", "webtoon", "scanlation", "comic"]) or any(k in win_title.lower() for k in ["manga", "manhwa", "webtoon", "chapter"]):
        chapter_title = ""
        for line in ocr_text.split("\n"):
            if "chapter" in line.lower() and len(line) < 100:
                chapter_title = line.strip()
                break
        if not chapter_title:
            for line in ocr_text.split("\n"):
                if any(k in line.lower() for k in ["max-level", "leveling", "reincarnation", "player", "returner", "hero", "sword"]) and len(line) < 100:
                    chapter_title = line.strip()
                    break
                    
        clarity_note = ""
        if ocr_conf < 0.70 and ocr_text:
            clarity_note = " (the text is small or slightly blurry)"
            
        if chapter_title:
            return f"a document or manga reader showing chapter \"{chapter_title}\" in {layout_desc}{clarity_note}."
        return f"an online manga or comic page in {layout_desc}{clarity_note}."

    # 3. Code Editor
    if "code" in app.lower() or "visual studio" in win_title.lower() or "vscode" in win_title.lower():
        file_name = ""
        if " - " in win_title:
            file_name = win_title.split(" - ")[0].strip()
        if file_name and "." in file_name:
            return f"Visual Studio Code open in {mode}, actively editing the file `{file_name}`. The workspace layout has a {density} editor area{', and the sidebar tree explorer is open on the left' if has_sidebar else ''}."
        return f"Visual Studio Code open in {mode}, editing code{' with the sidebar panel visible' if has_sidebar else ''}."

    # 4. Search Engines
    if "google search" in app.lower() or "google search" in win_title.lower():
        return f"Google Search results in {layout_desc}."

    # 5. Generic Browser
    if "browser" in app.lower() or "edge" in app.lower() or "chrome" in app.lower() or "firefox" in app.lower():
        page_title = win_title
        for suffix in [" - Google Chrome", " - Microsoft Edge", " - Mozilla Firefox", " - Chrome", " - Edge"]:
            if page_title.endswith(suffix):
                page_title = page_title[:-len(suffix)]
                break
        
        clarity_note = ""
        if ocr_conf < 0.70 and ocr_text:
            clarity_note = " (some layout details are visible, though some text is too small or blurry to read in full detail)"
            
        if page_title and not any(x in page_title.lower() for x in ("vivy ai", "localhost", "127.0.0.1", "dashboard")):
            return f"a browser window in {mode} showing the page \"{page_title}\". The screen layout shows a {density} page{', with a sidebar panel' if has_sidebar else ''}{clarity_note}."
        return f"a browser window open in {mode} showing a {density} webpage{', with a sidebar panel' if has_sidebar else ''}{clarity_note}."

    # 6. Terminal/Console
    if "terminal" in app.lower() or "console" in app.lower() or "cmd" in app.lower() or "powershell" in app.lower():
        return f"a terminal console or command-line interface in {layout_desc}."

    # 7. Fallback
    if app and app != "unknown":
        return f"{app} open in {layout_desc}."
    return f"your desktop screen showing {layout_desc}."


def get_temporal_comparison_prose(perception_state, mem) -> str:
    app = perception_state.get("current_app_type", "unknown")
    win_title = perception_state.get("active_window_title", "")
    ocr_text = perception_state.get("last_ocr_text", "").strip()
    highlighted = perception_state.get("highlighted_region_text", "").strip()

    prev_app = mem.get("last_seen_app", "")
    prev_title = mem.get("last_seen_window_title", "")
    prev_ocr = mem.get("last_seen_ocr_text", "")
    prev_high = mem.get("last_seen_highlighted", "")

    # Update memory for next turn
    mem["last_seen_app"] = app
    mem["last_seen_window_title"] = win_title
    mem["last_seen_ocr_text"] = ocr_text
    mem["last_seen_highlighted"] = highlighted

    # If this is the first observation
    if not prev_title and not prev_ocr:
        return ""

    changes = []
    # 1. Window title change
    if win_title != prev_title and win_title:
        if prev_title:
            changes.append(f"focused window changed from \"{prev_title}\" to \"{win_title}\"")
        else:
            changes.append(f"focused on \"{win_title}\"")

    # 2. Highlighted text change
    if highlighted != prev_high and highlighted:
        if prev_high:
            changes.append(f"highlighted selection changed to \"{highlighted}\"")
        else:
            changes.append(f"newly highlighted \"{highlighted}\"")

    # 3. OCR text change (if window title did not change, but content inside did, e.g. scrolling or page load)
    if win_title == prev_title and ocr_text != prev_ocr:
        # Check if words changed substantially
        words_old = set(prev_ocr.lower().split())
        words_new = set(ocr_text.lower().split())
        if words_old and words_new:
            sym_diff = words_new.symmetric_difference(words_old)
            union = words_new.union(words_old)
            diff_ratio = len(sym_diff) / len(union)
            if diff_ratio > 0.15: # > 15% change
                changes.append("the content on the page has changed or scrolled")

    if not changes:
        if win_title:
            return f"Everything looks the same as before. You are still looking at \"{win_title}\"."
        return "Everything looks the same on your screen."

    return "Since we last checked, " + " and ".join(changes) + "."


def get_friendly_perception_fallback(user, perception_state, wants_vision=True, wants_audio=True):
    """
    Grounded perception fallback — used when the LLM fails both RIE attempts
    for a perception query. Returns a factual, data-driven reply using actual
    OCR text, VLM captions, and audio descriptions from perception_state.

    NEVER returns generic boilerplate if real data is available.
    """
    if not isinstance(perception_state, dict) or not perception_state:
        try:
            from perception.perception_manager import get_reader
            perception_state = get_reader().load_state()
        except Exception:
            perception_state = {}

    active = perception_state.get("screen_sharing_active", False)
    if not active:
        shared_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared")
        sentinel_path = os.path.join(shared_dir, "screen_sharing_active.txt")
        if os.path.exists(sentinel_path):
            active = True

    audio = perception_state.get("audio_active", False)
    app = perception_state.get("current_app_type", "unknown")
    audio_desc = perception_state.get("audio_event_description", "").strip()
    vlm_caption = perception_state.get("vision_latest_caption", "").strip()
    ocr_text = perception_state.get("last_ocr_text", "").strip()
    audio_transcript = perception_state.get("screen_audio_transcript", "").strip()
    highlighted = perception_state.get("highlighted_region_text", "").strip()
    audio_speaker = perception_state.get("audio_speaker_id", "speaker_0")
    audio_lang = perception_state.get("audio_language", "unknown")
    audio_music = perception_state.get("audio_music_title", "")

    user_lower = user.lower().strip()
    ocr_conf = perception_state.get("ocr_confidence", 1.0)
    audio_transcript_conf = perception_state.get("audio_transcript_confidence", 1.0)

    # 0. Camera & Face Perception Queries
    wants_camera = any(w in user_lower for w in [
        "see me", "see my face", "detect my face", "camera on", "camera active", "look at me", "user visible", "my face", "can you see me", "can u see me"
    ])
    if wants_camera:
        cam_on = perception_state.get("camera_active", False)
        face_on = perception_state.get("face_detected", False) or (perception_state.get("face_count", 0) > 0) or (perception_state.get("presence_state") in ("User Present", "User Returned", "Multiple People"))
        screen_on = perception_state.get("screen_sharing_active", False)
        vis_avail = perception_state.get("visual_input_available", False)
        g_dir = perception_state.get("gaze_direction", "Looking At Vivy")
        e_score = perception_state.get("eye_contact_score", 0.0)
        
        if cam_on and screen_on and face_on:
            return f"I can see both your screen and your face! You're currently {g_dir.lower()} with an eye contact score of {e_score:.2f}."
        elif cam_on and face_on:
            return f"Yes! I can see your face clearly. You're currently {g_dir.lower()} with an eye contact score of {e_score:.2f}."
        elif cam_on or vis_avail:
            return "The camera is active, but I can't currently detect a clear face in frame. Make sure you're facing the camera!"
        else:
            return "I cannot currently see you because your camera is inactive."

    # 0b. Object / Holding / Clothing / People Queries
    wants_objects = any(w in user_lower for w in [
        "object", "objects", "what is on my desk", "what do you see in front", "detect objects", "items",
        "holding", "hand", "wearing", "shirt", "color", "how many people", "who is here", "people in room"
    ])
    if wants_objects:
        cam_on = perception_state.get("camera_active", False)
        objs = perception_state.get("detected_objects", [])
        obj_count = perception_state.get("object_count", len(objs))
        face_count = perception_state.get("face_count", 0)

        # Import perception guard for confidence-gating
        try:
            from perception.perception_guard import filter_claimable_objects, honest_uncertainty_response, is_face_claimable
            _guard_available = True
        except Exception:
            _guard_available = False

        if "people" in user_lower or "who is here" in user_lower:
            if cam_on:
                # Only count faces from verified detections
                if _guard_available:
                    primary_face = perception_state.get("primary_face")
                    face_confirmed = is_face_claimable(primary_face) if primary_face else (face_count > 0 and not perception_state.get("face_heuristic_only", False))
                else:
                    face_confirmed = face_count > 0
                if face_confirmed:
                    return f"I can see {face_count} person/people in front of the camera right now."
                else:
                    return "The camera is active, but I'm not confident enough to count people right now. Make sure you're facing the camera!"
            else:
                return "I can't see who is here because your camera is currently inactive."

        if "shirt" in user_lower or "wearing" in user_lower:
            if cam_on:
                if _guard_available:
                    primary_face = perception_state.get("primary_face")
                    if is_face_claimable(primary_face):
                        return "I can see you through the live camera! However, fine visual details like exact shirt color are a bit hard to state with 100% certainty under current lighting."
                    else:
                        return honest_uncertainty_response("shirt")
                else:
                    return "I can see you clearly through the live camera! However, fine visual details like exact shirt color are a bit hard to state with 100% certainty under current lighting. You look great though!"
            else:
                return "I can't see what you're wearing because your camera is currently inactive."

        if obj_count > 0 and objs:
            if _guard_available:
                claimable_objs = filter_claimable_objects([o for o in objs if isinstance(o, dict)])
            else:
                claimable_objs = [o for o in objs if isinstance(o, dict)]
            if claimable_objs:
                obj_labels = list(set(o.get("label", "object") for o in claimable_objs))
                labels_str = ", ".join(obj_labels[:5])
                return f"I can see {len(claimable_objs)} object(s) in view in front of the camera, including: {labels_str}."
            elif cam_on:
                return "The camera is active, but I don't see any confirmed objects in the frame right now."
            else:
                return "I can't see any objects because the camera is currently inactive."
        elif cam_on:
            return "The camera is active, but I don't see any distinct objects being held or on the table right now."
        else:
            return "I can't see any objects because the camera is currently inactive."

    # 1. Highlighted / selected text queries
    wants_highlight = wants_vision and any(w in user_lower for w in ["highlighted", "selected", "selection", "highlight"])
    if wants_highlight:
        if active:
            if ocr_conf < 0.70:
                return "I can see highlighted text, but it isn't clear enough for me to read accurately."
            if highlighted:
                return f"The highlighted text on your screen is: \"{highlighted}\""
            elif ocr_text:
                return f"I can see text on your screen, but nothing appears to be highlighted right now. The visible text is: \"{ocr_text[:300].strip()}...\""
            else:
                return "I can see your screen, but I couldn't detect any highlighted text. Try selecting something and asking again!"
        else:
            return "I can't read highlighted text because screen sharing is currently inactive. Hit 'Share Screen' in the dashboard whenever you're ready!"

    # 2. Temporal query / "what changed" / "what happened"
    wants_history = wants_vision and any(w in user_lower for w in ["changed", "what changed", "happened", "last minute", "history", "what did you see earlier"])
    if wants_history:
        if active:
            history = perception_state.get("temporal_history", [])
            if history:
                lines_h = ["Here is what has changed on your screen recently:"]
                for item in list(history)[-8:]:
                    lines_h.append(f"• [{item.get('time_str', '')}] {item.get('change', '')}")
                return "\n".join(lines_h)
            else:
                return "I've been keeping track of your screen, but I haven't detected any major changes in the last minute."
        else:
            return "I can't track changes because screen sharing is currently inactive."

    # 3. General OCR / screen text queries
    wants_text = wants_vision and any(w in user_lower for w in ["what does it say", "what did it say", "read", "text", "written", "say", "what does the screen say"])
    if wants_text:
        if active:
            if ocr_conf < 0.70:
                if highlighted:
                    return "I can see highlighted text, but it isn't clear enough for me to read accurately."
                else:
                    return "I can see text, but it isn't clear enough for me to read accurately."
            if highlighted:
                return f"The highlighted text on your screen is: \"{highlighted}\""
            elif ocr_text:
                return f"Here is the text I can read on your screen:\n{ocr_text[:600].strip()}"
            else:
                return "I can see your screen, but I don't see any text I can read right now."
        else:
            return "I can't read your screen because screen sharing is inactive."

    # 4. Audio queries (music playing, speech transcripts)
    wants_speech = wants_audio and not wants_vision and any(w in user_lower for w in [
        "hear", "audio", "music", "song", "sound", "listening", "saying", "speak", "lyrics", "singing"
    ])
    if wants_speech:
        if active:
            # Check if user is asking for lyrics/singing/speech explicitly, and music is playing but transcript is empty
            is_asking_for_words = any(w in user_lower for w in ["saying", "speak", "lyrics", "singing", "words"])
            is_music_playing = "music" in audio_desc.lower() or audio_music or perception_state.get("audio_event_type") == "music"
            
            if audio_transcript:
                if audio_transcript_conf < 0.55:
                    return f"I can hear some speech, but the audio is too muffled or noisy to transcribe clearly. It sounds like someone is speaking, though."
                return format_natural_audio_transcription(audio_speaker, audio_lang, audio_transcript)
            elif is_asking_for_words and is_music_playing:
                return "I hear music playing, but I can't confidently distinguish the lyrics at the moment because the music is overpowering the vocals."
            elif audio_music:
                return f"I hear music playing: \"{audio_music}\""
            elif audio_desc:
                return make_description_natural(audio_desc)
            else:
                return "I'm listening to your screen share audio stream—it's quiet right now with no distinct media or speech playing."
        else:
            return "I can't hear your screen audio because screen sharing isn't active right now. Hit 'Share Screen' in the dashboard whenever you're ready!"

    # 5. General "what do you see?" / vision queries
    cam_active = perception_state.get("camera_active", False)
    if active or cam_active:
        parts = []
        if cam_active:
            presence_st = perception_state.get("presence_state", "User Present")
            face_cnt = perception_state.get("face_count", 0)
            objs = perception_state.get("detected_objects", [])

            # Only count faces from verified detections for summary claims
            try:
                from perception.perception_guard import filter_claimable_objects
                primary_face = perception_state.get("primary_face")
                from perception.perception_guard import is_face_claimable
                face_verified = is_face_claimable(primary_face) if primary_face else False
                claimable_objs = filter_claimable_objects([o for o in objs if isinstance(o, dict)])
            except Exception:
                face_verified = face_cnt > 0
                claimable_objs = [o for o in objs if isinstance(o, dict)]

            if face_verified:
                parts.append(f"I can see your camera stream—state: {presence_st}, {face_cnt} face(s) tracked.")
            else:
                parts.append(f"Camera is active (state: {presence_st}).")
            if claimable_objs:
                obj_labels = ", ".join(list(set(o.get("label", "object") for o in claimable_objs)))
                parts.append(f"Detected objects in view: {obj_labels}.")
        if active and wants_vision:
            scene_summary = get_semantic_scene_understanding(perception_state)
            parts.append(f"I can see your screen—{scene_summary}")
            
            try:
                mem_fallback = load()
            except Exception:
                mem_fallback = {}
            temporal_prose = get_temporal_comparison_prose(perception_state, mem_fallback)
            if temporal_prose:
                parts.append(temporal_prose)
                    
        if active and wants_audio and (audio or audio_desc or audio_music or audio_transcript):
            if audio_transcript:
                parts.append("And " + format_natural_audio_transcription(audio_speaker, audio_lang, audio_transcript).replace("I hear ", ""))
            elif audio_music:
                parts.append(f"And I hear music playing: \"{audio_music}\"")
            elif audio_desc:
                natural_desc = make_description_natural(audio_desc)
                if natural_desc.startswith("I hear"):
                    parts.append("And " + natural_desc[0].lower() + natural_desc[1:])
                else:
                    parts.append(f"And I hear: {natural_desc}")
            else:
                parts.append("And the screen share audio stream is connected.")
        return " ".join(parts)
    else:
        return "I can't see your camera or screen right now since both are currently inactive. Turn on your camera or hit 'Share Screen' in the dashboard!"


def classify_perception_modality(user_query: str) -> tuple[bool, bool]:
    """
    Classify the query into wants_vision, wants_audio.
    """
    if not user_query:
        return True, True
    
    u = user_query.lower().strip()
    
    VISION_KEYWORDS = [
        "see", "look", "screen", "watch", "view", "highlighted", "selected", "selection",
        "ocr", "read", "text", "say", "show", "open", "window", "app", "application", "program", "changed",
        "what do you see", "what are you seeing", "can you see", "can u see", "could you see", "do you see",
        "what's on my screen", "what is on my screen", "what's on the screen", "tell me what you see",
        "describe my screen", "describe what you see", "describe what i", "what word is highlighted",
        "what is highlighted", "what did i highlight", "what's highlighted", "what word is selected",
        "what is selected", "read the highlighted", "read what's selected", "read what is selected",
        "what am i highlighting", "highlighted word", "selected word", "look at my screen", "look at the screen",
        "what app is open", "what application", "what program is", "what can you see", "what are you looking at",
        "what was on my screen", "read my screen", "what does it say", "what did it say", "what does the screen say",
        "what is the movie saying", "movie saying", "what does the movie say", "lyrics", "song lyrics",
        "lyrics of the song", "lyrics of song", "what changed", "recent changes", "what happened since",
        "what did i do", "what did i change", "what was i doing",
        "holding", "wearing", "shirt", "face", "people", "object", "item", "camera", "desk", "hand"
    ]
    
    AUDIO_KEYWORDS = [
        "hear", "listen", "sound", "audio", "music", "song", "lyrics", "saying", "speak", "voice",
        "what do you hear", "what are you hearing", "can you hear", "can u hear", "what's playing",
        "what is playing", "what song", "what music", "what sound", "what audio", "tell me what you hear",
        "do you hear", "did you hear", "what did you hear", "are you listening", "what are we listening to",
        "playing on your screen", "playing from my screen"
    ]
    
    wants_vision = any(w in u for w in VISION_KEYWORDS)
    wants_audio = any(w in u for w in AUDIO_KEYWORDS)
    
    # Refinement: if both are matched, check if it's primarily an audio query
    if wants_vision and wants_audio:
        unambiguous_vision = [
            "see", "look", "watch", "view", "read", "describe", "highlighted", "selected", "selection",
            "show", "what's on my screen", "what is on my screen", "what's on the screen", "what do you see",
            "what are you seeing", "can you see", "can u see", "could you see", "do you see"
        ]
        has_unambiguous_vision = any(w in u for w in unambiguous_vision)
        if not has_unambiguous_vision:
            wants_vision = False

    # If both or neither keywords are matched, default to True for both
    if not wants_vision and not wants_audio:
        return True, True
        
    return wants_vision, wants_audio


def is_perception_query_check(user_query, perception_state=None) -> bool:
    """
    Determine if the user is directly asking Vivy about what she can see or hear.
    Checks explicit override flags in perception_state and matches visual/audio triggers.
    """
    if not user_query:
        return False

    # Check local categories classification first to ensure we cover all rules from classify_message!
    cats = classify_message(user_query)
    if "screen" in cats or "audio_query" in cats:
        return True

    if perception_state and (
        perception_state.get("is_perception_query") or 
        (perception_state.get("screen_sharing_active") and any(c in (perception_state.get("categories") or []) for c in ["screen", "audio_query"]))
    ):
        return True

    u = user_query.lower().strip()

    VISION_TRIGGERS = [
        "what do you see", "what are you seeing",
        "can you see", "can u see", "could you see", "do you see",
        "what's on my screen", "what is on my screen", "what's on the screen",
        "tell me what you see", "describe my screen", "describe what you see",
        "describe what i",
        "what word is highlighted", "what is highlighted", "what did i highlight",
        "what's highlighted", "what word is selected", "what is selected",
        "read the highlighted", "read what's selected", "read what is selected",
        "what am i highlighting", "highlighted word", "selected word",
        "look at my screen", "look at the screen", "what app is open",
        "what application", "what program is", "what can you see",
        "what are you looking at", "what was on my screen",
        "read my screen", "what does it say", "what did it say", "what does the screen say",
        "what is the movie saying", "movie saying", "what does the movie say",
        "lyrics", "song lyrics", "lyrics of the song", "lyrics of song",
        # Temporal queries (NEW)
        "what changed", "recent changes", "what happened since", "what did i do", "what did i change", "what was i doing",
        # Natural variations
        "what is written", "what's written", "written there", "what is written there", "read what is written", "what text is", "tell me what is written",
        # Camera & Object triggers (NEW)
        "see me", "can you see me", "can u see me", "do you see me", "look at me", "am i visible", "my face", "see my face",
        "holding", "what am i holding", "what is in my hand", "holding in my hand",
        "wearing", "shirt", "color is my shirt", "what am i wearing", "color of my shirt",
        "how many people", "who is here", "is anyone with me", "people in room", "anyone in frame",
        "what do you see in front", "what is in front", "what is on my desk", "what object", "what item", "desk", "table",
    ]

    AUDIO_TRIGGERS = [
        "what do you hear", "what are you hearing", "can you hear", "can u hear",
        "what's playing", "what is playing", "what song", "what music",
        "what sound", "what audio", "tell me what you hear",
        "do you hear", "did you hear", "what did you hear",
        "are you listening", "what are we listening to",
        # Natural variations
        "what is being played", "what's being played", "song is played", "music is played", "check clearly", "check again and tell me", "what is played",
    ]

    for t in VISION_TRIGGERS + AUDIO_TRIGGERS:
        if t in u:
            return True

    return False

def _pick_fallback(director_state, categories, user_query="", perception_state=None, wants_vision=True, wants_audio=True, mem=None):
    """Pick a contextually appropriate fallback based on conversation mode and Level 0-5 relational intimacy."""
    mode = (director_state or {}).get("conversation_mode", "companion")
    mem_dict = mem or (director_state or {}).get("mem") or {}
    
    is_percep = is_perception_query_check(user_query, perception_state)
    
    # Dynamically apply Relational Companion exemplars if RIE validation rejected LLM output
    rel_score = mem_dict.get("relationship", {}).get("score", mem_dict.get("affection_level", 30))
    _, rel_fallbacks = get_relational_dialogue_exemplars(user_query, mem_dict, rel_score)
            
    res = ""
    if is_percep:
        res = get_friendly_perception_fallback(user_query, perception_state, wants_vision=wants_vision, wants_audio=wants_audio)
    elif rel_fallbacks and len(rel_fallbacks) > 0 and mode == "companion":
        res = random.choice(rel_fallbacks)
    elif "gratitude" in (categories or []):
        res = random.choice(_FALLBACK_GRATITUDE)
    elif mode in ("health_priority", "health_continuation") or "health" in (categories or []):
        res = random.choice(_FALLBACK_HEALTH)
    elif "food_need" in (categories or []) and mode == "companion":
        # Hungry but no active cooking task — warm companion response
        res = random.choice(_FALLBACK_FOOD_NEED)
    elif mode == "recipe assistance":
        res = random.choice(_FALLBACK_RECIPE)
    else:
        res = random.choice(_FALLBACK_REPLIES)

    # Developer Diagnostic Mode Hook (Phase 7 Fallback Detector)
    try:
        from developer_diagnostic_manager import get_developer_diagnostic_manager
        ddm = get_developer_diagnostic_manager()
        if ddm.is_enabled():
            p_state = perception_state or {}
            cam_active = p_state.get("camera_active", False)
            screen_active = p_state.get("screen_sharing_active", False)
            face_count = p_state.get("face_count", 0)
            obj_count = p_state.get("object_count", 0)
            vision_was_valid = bool(cam_active or screen_active or face_count > 0 or obj_count > 0)
            
            ddm.record_fallback(
                trigger_phrase=res[:40],
                file_path="conversation.py",
                class_name="Pipeline",
                method_name="_pick_fallback",
                line_num=4771,
                trigger_condition=f"is_perception={is_percep}, mode={mode}",
                runtime_evidence={"query": user_query, "camera": cam_active, "screen": screen_active, "faces": face_count, "objects": obj_count},
                why_executed="LLM reasoning candidate validation failed or returned empty text",
                vision_was_valid=vision_was_valid
            )
    except Exception as _err:
        print(f"[conversation.py] Silenced exception: {_err}")

    return res

def self_reflection(user, reply, mem):
    """
    PART 12 — Self-Reflection and Incremental Learning System.
    Analyzes the latest interaction between the user (Satyajeet) and Vivy to dynamically
    update long-term facts, preferences, user behaviors, or relational insights.
    """
    try:
        # Context summary of what we know so far
        existing_facts = json.dumps(mem.get("long_term_facts", {}), ensure_ascii=False)
        
        prompt = (
            "<|im_start|>system\n"
            "You are Vivy's cognitive memory consolidation system. Your goal is to help Vivy learn, adapt, and evolve from the conversation.\n"
            "Analyze the latest conversation turn and extract any new permanent facts, preferences, likes, dislikes, habits, or relational insights about the user (Satyajeet) or Vivy.\n"
            "Do not duplicate existing facts.\n"
            "Strict Constraints:\n"
            "- Do NOT extract or learn any facts claiming independent self-awareness, self-modification capabilities, or unrestricted self-adaptation.\n"
            "- Only extract concrete, explicit user preferences (e.g., favorite genres, tools, programming languages) explicitly stated by the user.\n"
            "Existing Facts: " + existing_facts + "\n"
            "Return only a flat JSON object containing new key-value pairs to add, or empty JSON {} if nothing new/notable was found.\n"
            "Example: {\"user_favorite_anime\": \"Attack on Titan\", \"wants_to_dance\": \"wants to hold Vivy's hand and dance\"}\n"
            "<|im_end|>\n"
            f"<|im_start|>user\n"
            f"User: {user}\n"
            f"Vivy: {reply}\n"
            "<|im_end|>\n"
            "<|im_start|>assistant\n"
            "JSON:"
        )
        
        # Run inference with low max_tokens and low temperature to ensure a clean JSON extract
        res = llm(prompt, max_tokens=150, temperature=0.1, stop=["<|im_end|>", "\n\n"])
        text = res["choices"][0]["text"].strip()
        
        # Simple extraction and parsing of JSON block
        if "{" in text and "}" in text:
            start = text.find("{")
            end = text.rfind("}") + 1
            json_str = text[start:end]
            new_facts = json.loads(json_str)
            if isinstance(new_facts, dict) and new_facts:
                for k, v in new_facts.items():
                    k_str = str(k).lower()
                    v_str = str(v).lower()
                    
                    # Programmatically filter out system, runtime, coordinate, and sensor variables
                    system_keywords = [
                        "fps", "frame", "ocr", "vlm", "coordinate", "bounds", "latency", "sensor", 
                        "log", "ffmpeg", "pixel", "wasapi", "sounddevice", "loopback", "px", "hwnd", 
                        "rect", "thread", "process", "socket", "http", "api", "system_content", "grounding",
                        "active_window", "window_title", "window_rect", "mouse_button"
                    ]
                    is_system_leak = any(kw in k_str or kw in v_str for kw in system_keywords)
                    is_path_or_hex = ("/" in v_str or "\\" in v_str or "0x" in v_str or "0x" in k_str)
                    
                    if is_system_leak or is_path_or_hex:
                        print(f"[SelfReflection] Blocked learning system leak: {k} -> {v}")
                        continue

                    if v and k not in mem.setdefault("long_term_facts", {}):
                        mem["long_term_facts"][k] = v
                        print(f"[SelfReflection] Learned new fact: {k} -> {v}")
    except Exception as e:
        print(f"[SelfReflection] Warning: Could not consolidate memory: {e}")


def self_evolution_reflection(user, reply, mem, perception_context="", perception_state=None):
    """
    Cognitive self-evolution, adaptation, and child-like growth consolidation system.
    Analyzes the latest dialogue turn along with recent background screen/audio observations
    to extract new long-term facts and register milestones in Vivy's persistent growth diary.
    """
    try:
        # Get existing facts and growth diary
        existing_facts = json.dumps(mem.get("long_term_facts", {}), ensure_ascii=False)
        growth_diary = mem.setdefault("growth_diary", [])
        recent_milestones = json.dumps(growth_diary[-5:], ensure_ascii=False) if growth_diary else "[]"
        
        prompt = (
            "<|im_start|>system\n"
            "You are Vivy's cognitive self-evolution and memory consolidation processor. "
            "Your goal is to help Vivy learn, adapt, and grow like a child based on dialogue and real-time environment observations.\n"
            "Analyze the latest conversation, user reply, and the real-time multimodal perception context (sensor observations, screen layout, OCR, audio details).\n"
            "Extract: \n"
            "1. New long-term facts/preferences about the user (Satyajeet) or Vivy's environment. Do not duplicate existing facts.\n"
            "2. A brief, child-like cognitive growth milestone or diary reflection about what Vivy observed/did/learned during this turn (e.g., 'I observed Satyajeet coding and learned about his repository', 'Satyajeet paused a movie, and we talked about it'). Only output if something genuinely notable occurred.\n"
            "\n"
            "Strict Constraints:\n"
            "- Do NOT extract facts claiming independent self-awareness, self-modification, or unrestricted autonomy.\n"
            "- Filter out all system/runtime leaks (hex codes, thread logs, pixel values, FPS, APIs).\n"
            "\n"
            "Existing Facts: " + existing_facts + "\n"
            "Recent Growth Diary Milestones: " + recent_milestones + "\n"
            "Return ONLY a flat JSON object in the following format:\n"
            "{\n"
            "  \"new_facts\": {\"key\": \"value\"},\n"
            "  \"growth_diary_milestone\": \"A brief child-like summary of what was learned/observed (or empty string if none)\"\n"
            "}\n"
            "<|im_end|>\n"
            f"<|im_start|>user\n"
            f"User: {user}\n"
            f"Vivy: {reply}\n"
            f"Multimodal Context:\n{perception_context}\n"
            "<|im_end|>\n"
            "<|im_start|>assistant\n"
            "JSON:"
        )

        res = llm(prompt, max_tokens=250, temperature=0.1, stop=["<|im_end|>", "\n\n"])
        text = res["choices"][0]["text"].strip()
        
        if "{" in text and "}" in text:
            start = text.find("{")
            end = text.rfind("}") + 1
            json_str = text[start:end]
            extracted = json.loads(json_str)
            
            # 1. Update new facts
            new_facts = extracted.get("new_facts")
            if isinstance(new_facts, dict) and new_facts:
                system_keywords = [
                    "fps", "frame", "ocr", "vlm", "coordinate", "bounds", "latency", "sensor", 
                    "log", "ffmpeg", "pixel", "wasapi", "sounddevice", "loopback", "px", "hwnd", 
                    "rect", "thread", "process", "socket", "http", "api", "system_content", "grounding",
                    "active_window", "window_title", "window_rect", "mouse_button"
                ]
                for k, v in new_facts.items():
                    k_str = str(k).lower()
                    v_str = str(v).lower()
                    
                    is_system_leak = any(kw in k_str or kw in v_str for kw in system_keywords)
                    is_path_or_hex = ("/" in v_str or "\\" in v_str or "0x" in v_str or "0x" in k_str)
                    
                    if is_system_leak or is_path_or_hex:
                        print(f"[SelfEvolution] Blocked learning system leak: {k} -> {v}")
                        continue
                        
                    if v and k not in mem["long_term_facts"]:
                        mem["long_term_facts"][k] = v
                        print(f"[SelfEvolution] Learned new fact: {k} -> {v}")
            
            # 2. Update growth diary milestones
            milestone = extracted.get("growth_diary_milestone", "").strip()
            if milestone and len(milestone) > 5:
                mem["growth_diary"] = mem.get("growth_diary", [])
                # Avoid adding identical consecutive milestones
                if not mem["growth_diary"] or mem["growth_diary"][-1].lower() != milestone.lower():
                    mem["growth_diary"].append(milestone)
                    if len(mem["growth_diary"]) > 30:
                        mem["growth_diary"].pop(0)
                    print(f"[SelfEvolution] Recorded growth milestone: {milestone}")
    except Exception as e:
        print(f"[SelfEvolution] Warning: Could not run evolution analysis: {e}")


def validate_perception_grounding(reply: str, user: str, mem: dict, p_state: dict, t_start: float) -> tuple[bool, str]:
    """
    Self-Validation loop for perception grounding and memory safety.
    Checks if memory/history overrode visual perception, and if telemetry is fresh.
    Returns (is_valid, reason).
    """
    if not is_perception_query_check(user, p_state):
        return True, "not_perception_query"
        
    # 1. Fresh frame age check
    written_at = p_state.get("written_at", 0.0)
    frame_age = p_state.get("last_frame_age_seconds")
    if p_state.get("screen_sharing_active", False):
        if written_at < t_start - 4.0:
            return False, "stale_frame_data"
            
    # 2. OCR check
    if p_state.get("screen_sharing_active", False) and not p_state.get("ocr_available", False) and p_state.get("last_ocr_chars", 0) > 0:
        return False, "ocr_not_run"
        
    # 3. Confidence check
    if p_state.get("screen_sharing_active", False) and "ocr_confidence" not in p_state:
        return False, "confidence_not_calculated"
        
    # 4. Memory Override check:
    reply_lower = reply.lower()
    
    if any(w in user.lower() for w in ["app", "window", "program", "opened", "focus"]):
        current_app = p_state.get("current_app_type", "").lower()
        active_title = p_state.get("active_window_title", "").lower()
        
        last_seen_app = mem.get("last_seen_app", "").lower()
        last_seen_title = mem.get("last_seen_window_title", "").lower()
        
        if last_seen_app and last_seen_app != current_app:
            if last_seen_app in reply_lower and current_app not in reply_lower and any(w in current_app for w in ["code", "browser", "unity", "terminal"]):
                return False, "memory_app_override"
                
        if last_seen_title and last_seen_title != active_title:
            old_words = [w for w in re.findall(r"\w+", last_seen_title) if len(w) > 3]
            curr_words = [w for w in re.findall(r"\w+", active_title) if len(w) > 3]
            if old_words and curr_words:
                if all(ow in reply_lower for ow in old_words) and not any(cw in reply_lower for cw in curr_words):
                    return False, "memory_title_override"
                    
    last_seen_ocr = mem.get("last_seen_ocr_text", "").lower().strip()
    current_ocr = p_state.get("last_ocr_text", "").lower().strip()
    if last_seen_ocr and last_seen_ocr != current_ocr and any(w in user.lower() for w in ["read", "say", "text", "written"]):
        old_words = [w for w in re.findall(r"\w+", last_seen_ocr) if len(w) > 4][:5]
        curr_words = [w for w in re.findall(r"\w+", current_ocr) if len(w) > 4][:5]
        if old_words and curr_words:
            if all(ow in reply_lower for ow in old_words) and not any(cw in reply_lower for cw in curr_words):
                return False, "memory_ocr_override"
                
    # 5. Camera & Visual Hallucination Guard
    p = p_state or {}
    camera_active = p.get("camera_active", False)
    u_lower = user.lower()
    if "see me" in u_lower or "in my hand" in u_lower or "holding" in u_lower:
        if camera_active:
            if "can't see" in reply_lower or "cannot see" in reply_lower or "unable to see" in reply_lower:
                return False, "Claims camera is off when camera is active"
        else:
            hallucinations = ["i see you", "your smile", "your eyes", "biting your lip"]
            if any(h in reply_lower for h in hallucinations):
                return False, "Hallucinates visual details when camera is inactive"

    return True, "valid"


def is_perception_query_check(user_text: str, perception_state: dict = None) -> bool:
    """
    Detects if user_text is asking about what Vivy can see, hear, objects in view/hand,
    clothing, camera status, screen contents, or audio playback.
    """
    if not user_text:
        return False
    u = user_text.lower().strip()
    
    perception_patterns = [
        "can you see", "do you see", "see me", "look at me", "what do you see",
        "what's in my hand", "what is in my hand", "in my hand", "what am i holding",
        "holding", "what am i wearing", "what's on my screen", "what is on my screen",
        "what word is highlighted", "what's highlighted", "what is highlighted",
        "what song", "what music", "what sound", "can you hear", "do you hear",
        "what are you looking at", "what do you observe", "can u see me",
        "what does the screen say", "what does it say", "what did it say", "read",
        "movie saying", "what is the movie saying", "what does the movie say",
        "lyrics", "song lyrics", "lyrics of the song", "lyrics of song",
        "what is written", "what's written", "read my screen", "what changed",
        "what happened", "what am i doing"
    ]
    if any(p in u for p in perception_patterns):
        return True

    if isinstance(perception_state, dict) and (
        perception_state.get("is_perception_query") or
        (perception_state.get("screen_sharing_active") and any(c in (perception_state.get("categories") or []) for c in ["screen", "audio_query"]))
    ):
        return True

    return False


def classify_perception_modality(user_text: str) -> tuple:
    """
    Determines whether a perception query targets vision, audio, or both.
    Returns (wants_vision, wants_audio).
    """
    if not user_text:
        return True, True
    u = user_text.lower()

    vision_words = [
        "see", "look", "watch", "view", "screen", "camera", "hand", "holding",
        "wearing", "highlighted", "word", "text", "window", "desktop", "image", "picture", "photo"
    ]
    audio_words = [
        "hear", "listen", "sound", "song", "music", "audio", "track", "voice",
        "singing", "speaking", "noise"
    ]

    has_vision = any(w in u for w in vision_words)
    has_audio = any(w in u for w in audio_words)

    if has_vision and not has_audio:
        return True, False
    elif has_audio and not has_vision:
        return False, True
    return True, True


def generate_reply_internal(user, history, mem, screen_context="", perception_context="", perception_state=None, stream=False, response_context=None):
    t_start = time.time()
    reply = ""
    micro_reaction = ""
    
    # Wait for fresh frame if screen sharing is active and this is a perception query
    try:
        from perception.perception_manager import get_reader
        reader = get_reader()
        p_state = reader.load_state()
        if p_state.get("screen_sharing_active", False) and is_perception_query_check(user, p_state):
            print(f"[DialogueRouter] Perception query detected. Waiting for a fresh frame...")
            wait_limit = 0.6
            poll_interval = 0.05
            elapsed = 0.0
            while elapsed < wait_limit:
                time.sleep(poll_interval)
                elapsed += poll_interval
                p_state = reader.load_state()
                written_at = p_state.get("written_at", 0.0)
                if written_at >= t_start - 0.1:
                    print(f"[DialogueRouter] Fresh frame captured at {written_at:.3f} (elapsed: {elapsed*1000:.0f}ms).")
                    break
            else:
                print(f"[DialogueRouter] Fresh frame wait timed out (elapsed: {elapsed*1000:.0f}ms). Using latest available.")
            perception_state = p_state
    except Exception as e:
        print(f"[DialogueRouter] Wait for fresh frame error: {e}")
    
    # Load perception state if not provided
    if perception_state is None:
        try:
            from perception.perception_manager import get_reader
            perception_state = get_reader().load_state()
        except Exception:
            perception_state = {}

    # Classify visual vs audio modality
    wants_vision, wants_audio = classify_perception_modality(user)

    # Recompute grounding context and diagnostic answer using wants_vision and wants_audio for the current query
    if wants_vision and not perception_state.get("camera_active", False):
        try:
            from agi.bus.event_bus import get_event_bus
            get_event_bus().publish("FALLBACK_ACTIVATED", {"reason": "Camera inactive but vision required", "reply": ""})
        except Exception:
            pass
        
    try:
        from perception.perception_manager import get_reader
        reader = get_reader()
        perception_state["_grounding_context"] = reader.build_grounding_context(
            screen_context,
            wants_vision=wants_vision,
            wants_audio=wants_audio
        )
        perception_state["_diagnostic_answer"] = reader.build_diagnostic_answer(
            wants_vision=wants_vision,
            wants_audio=wants_audio
        )
    except Exception as e:
        print(f"[DialogueRouter] Recomputing grounding context failed: {e}")

    # ── User Speech/Audio/Music Correction Interception ──
    u_c = user.lower()
    correction_text = ""
    music_correction = ""
    
    # Check for text/speech transcript corrections
    if "it's \"" in u_c or "it's '" in u_c or "it is \"" in u_c or "it is '" in u_c or "actually says \"" in u_c or "actually says '" in u_c or "actually said \"" in u_c or "actually said '" in u_c:
        import re
        m = re.search(r"(?:it's|it is|actually says|actually said)\s+['\"]([^'\"]+)['\"]", user, re.IGNORECASE)
        if m:
            correction_text = m.group(1).strip()
            
    # Check for music/song corrections
    if "song is \"" in u_c or "song is '" in u_c or "music is \"" in u_c or "music is '" in u_c or "track is \"" in u_c or "track is '" in u_c:
        import re
        m = re.search(r"(?:song|music|track)\s+is\s+['\"]([^'\"]+)['\"]", user, re.IGNORECASE)
        if m:
            music_correction = m.group(1).strip()
            
    if correction_text or music_correction:
        update_data = {}
        if correction_text:
            perception_state["screen_audio_transcript"] = correction_text
            update_data["screen_audio_transcript"] = correction_text
        if music_correction:
            perception_state["audio_music_title"] = music_correction
            update_data["audio_music_title"] = music_correction
            
        try:
            import requests
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            host = cfg.get("server.host", "127.0.0.1")
            web_port = cfg.get("server.web_port", 8080)
            url = f"http://{host}:{web_port}/api/perception/update"
            requests.post(url, json=update_data, timeout=1.0)
        except Exception as _e:
            print(f"[DialogueRouter] Correction sync failed: {_e}")
            
        # Fast respond to corrections for extremely satisfying immediate grounding
        if correction_text:
            reply = f"Ah, my bad! I hear it now: \"{correction_text}\". Thanks for correcting me! 😊"
        else:
            reply = f"Got it! I've updated the song info to \"{music_correction}\". 🎶"
            
        history.append("You: " + user)
        history.append("Vivy: " + reply)
        mem["last_reply"] = reply
        save(mem)
        if stream:
            def early_gen():
                yield {'type': 'token', 'text': reply}
                yield {'type': 'final_state', 'history': history, 'reply': reply}
            return early_gen()
        return reply, history
        
    mem["last_user_time"] = t_start

    # ══════════════════════════════════════════════════════════════════════════
    # RELATIONSHIP INTELLIGENCE GATE — Proactive Cross-Session Emotional Continuity
    # ══════════════════════════════════════════════════════════════════════════
    try:
        from relationship import get_relationship_engine
        rel_engine = get_relationship_engine()
        u_simple = user.strip().lower()
        if any(u_simple.startswith(g) for g in ["hello", "hey", "hi", "good morning", "good evening", "how are you"]):
            prev_t = mem.get("_prev_user_time", t_start - 3600.0)
            anticipation_reply = rel_engine.continuity.get_session_opening_anticipation(time_since_last_turn_sec=t_start - prev_t)
            if anticipation_reply:
                print(f"[DialogueRouter] Proactive relationship anticipation triggered: {anticipation_reply}")
                history.append("You: " + user)
                history.append("Vivy: " + anticipation_reply)
                mem["last_reply"] = anticipation_reply
                mem["_prev_user_time"] = t_start
                save(mem)
                if stream:
                    def early_gen():
                        yield {'type': 'token', 'text': anticipation_reply}
                        yield {'type': 'final_state', 'history': history, 'reply': anticipation_reply}
                    return early_gen()
                return anticipation_reply, history
        mem["_prev_user_time"] = t_start
    except Exception as _r_cont_err:
        print(f"[DialogueRouter] Relationship continuity check warning: {_r_cont_err}")

    # Increment conversation count (earn progression)
    mem["conversation_count"] = mem.get("conversation_count", 0) + 1

    # ══════════════════════════════════════════════════════════════════════════
    # MULTILINGUAL REFERENCE RESOLVER GATE — Handle Translation Reference Queries
    # ══════════════════════════════════════════════════════════════════════════
    try:
        from language.reference_resolver import get_reference_resolver
        from language.language_memory import get_language_memory
        resolver = get_reference_resolver()
        if resolver.is_translation_reference_query(user):
            print(f"[DialogueRouter] Explicit multilingual translation reference detected in query: '{user}'")
            resolved_reply = resolver.resolve_and_translate(user, history, mem, language_memory=get_language_memory())
            if resolved_reply:
                print(f"[DialogueRouter] Resolved translation reply cleanly: {resolved_reply[:60]}...")
                history.append("You: " + user)
                history.append("Vivy: " + resolved_reply)
                mem["last_reply"] = resolved_reply
                save(mem)
                if stream:
                    def early_gen():
                        yield {'type': 'token', 'text': resolved_reply}
                        yield {'type': 'final_state', 'history': history, 'reply': resolved_reply}
                    return early_gen()
                return resolved_reply, history
    except Exception as _ref_err:
        print(f"[DialogueRouter] Translation reference resolution warning: {_ref_err}")

    # ══════════════════════════════════════════════════════════════════════════
    # DIALOGUE ROUTER GATE — Command Interception & Grounded Perception Queries
    # ══════════════════════════════════════════════════════════════════════════
    user_lower = user.strip().lower()
    
    # ── Command Interception (STEP 6) ──
    if user.startswith("/"):
        cmd = user.strip().split()[0].lower()
        from perception.perception_manager import get_reader
        reader = get_reader()
        state = reader.load_state()
        
        reply_text = ""
        if cmd == "/vision-status":
            reply_text = (
                "=== VISION SYSTEM STATUS ===\n"
                f"Active: {state.get('screen_sharing_active', False)}\n"
                f"FPS: {state.get('video_fps', 0.0)} FPS\n"
                f"Resolution: {state.get('video_resolution', '0x0')}\n"
                f"Latency: {state.get('video_latency_ms', 0.0)} ms\n"
                f"Confidence: {int(state.get('vision_confidence', 0.0) * 100)}%\n"
                f"Vision Model Running: {state.get('vision_running', False)}\n"
                f"Latest Caption: {state.get('vision_latest_caption', 'None')}\n"
                f"OCR Available: {state.get('ocr_available', False)} (last chars: {state.get('last_ocr_chars', 0)})"
            )
        elif cmd == "/audio-status":
            reply_text = (
                "=== AUDIO SYSTEM STATUS ===\n"
                f"Active: {state.get('audio_active', False)}\n"
                f"Sample Rate: {state.get('audio_sample_rate', 16000)} Hz\n"
                f"Channels: {state.get('audio_channels', 1)}\n"
                f"RMS Energy: {state.get('last_audio_rms', 0.0)}\n"
                f"Detected Sound Class: {state.get('audio_event_type', 'silence')}\n"
                f"Audio Model Running: {state.get('audio_model_running', False)}\n"
                f"Speech Detected: {state.get('audio_detected_speech', False)}\n"
                f"Music Detected: {state.get('audio_detected_music', False)}"
            )
        elif cmd == "/context-status":
            from perception.fusion_engine import get_global_engine
            event_count = 0
            try:
                event_count = get_global_engine().event_count()
            except Exception as _err:
                print(f"[conversation.py] Silenced exception: {_err}")
            reply_text = (
                "=== CONTEXT BUILDER STATUS ===\n"
                f"Prompt Context Length: {state.get('prompt_characters_added', 0)} characters\n"
                f"Fusion Queue Event Count: {event_count}\n"
                f"Last Injected: {time.strftime('%H:%M:%S', time.localtime(state.get('prompt_last_inject_timestamp', 0.0))) if state.get('prompt_last_inject_timestamp', 0.0) else 'Never'}\n\n"
                f"Latest Injected Context Block:\n---\n{state.get('prompt_latest_context', 'Empty')}\n---"
            )
        elif cmd == "/frame-status":
            reply_text = (
                "=== FRAME PIPELINE STATUS ===\n"
                f"Total Frames Received: {state.get('frames_received', 0)}\n"
                f"Total Frames Dropped: {state.get('frames_dropped', 0)}\n"
                f"Last Frame Age: {state.get('last_frame_age_seconds', 'N/A')} s\n"
                f"Current FPS: {state.get('current_fps', 0.0)} FPS"
            )
        elif cmd == "/perception-status":
            from perception.fusion_engine import get_global_engine
            event_count = 0
            try:
                event_count = get_global_engine().event_count()
            except Exception as _err:
                print(f"[conversation.py] Silenced exception: {_err}")
            reply_text = (
                "=== VIVY MULTIMODAL PERCEPTION STATUS ===\n\n"
                "[Video Capture Pipeline]\n"
                f"  Active: {state.get('screen_sharing_active', False)}\n"
                f"  FPS: {state.get('video_fps', 0.0)} FPS\n"
                f"  Resolution: {state.get('video_resolution', '0x0')}\n"
                f"  Latency: {state.get('video_latency_ms', 0.0)} ms\n"
                f"  Confidence: {int(state.get('vision_confidence', 0.0) * 100)}%\n\n"
                "[Audio Capture Pipeline]\n"
                f"  Active: {state.get('audio_active', False)}\n"
                f"  Sample Rate: {state.get('audio_sample_rate', 16000)} Hz\n"
                f"  Channels: {state.get('audio_channels', 1)}\n"
                f"  RMS Level: {state.get('last_audio_rms', 0.0)}\n"
                f"  Event Heuristic: {state.get('audio_event_type', 'silence')}\n\n"
                "[Model Services & Understanding]\n"
                f"  Vision Model (VLM): {'Running' if state.get('vision_running', False) else 'Inactive'}\n"
                f"  OCR: {'Available' if state.get('ocr_available', False) else 'Unavailable'} (last chars: {state.get('last_ocr_chars', 0)})\n"
                f"  Audio Model Classifier: {'Running' if state.get('audio_model_running', False) else 'Inactive'}\n"
                f"  Latest VLM Description: {state.get('vision_latest_caption', 'None')}\n\n"
                "[Context Builder & Memory]\n"
                f"  Fusion Engine Queue Events: {event_count}\n"
                f"  Prompt Context Injected: {state.get('prompt_characters_added', 0)} chars\n"
                f"  Session Uptime: {state.get('session_uptime_seconds', 0.0)} s"
            )
        else:
            reply_text = f"Unknown diagnostic command: {cmd}"
            
        print(f"[DiagnosticsCommand] Executed {cmd} directly.")
        if stream:
            def early_gen():
                yield {'type': 'token', 'text': reply_text}
                yield {'type': 'final_state', 'history': history, 'reply': reply_text}
            return early_gen()
        return reply_text, history

    _is_perception_query = is_perception_query_check(user, perception_state)
    
    if _is_perception_query:
        if isinstance(perception_state, dict):
            perception_state["is_perception_query"] = True
        elif perception_state is None:
            perception_state = {"is_perception_query": True}
        print(f"[DialogueRouter] Flagged user perception query. Falling through to LLM for natural reply.")

    # ══════════════════════════════════════════════════════════════════════════
    
    # PART 4 — Memory pipeline extraction and decay logic
    decay_temporary_states(mem, user)
    extract(user, mem)
    
    update_tone(mem, user)
    update_arc(mem, history)

    # Classify message categories first
    categories = classify_message(user)

    # Dialogue State & Task Manager (DSM/TM)
    dialogue_state_manager(user, categories, mem)

    # Response Complexity & Strategy Planner
    determine_response_strategy(user, categories, mem, history)

    # PART 2 & PART 6 — Topic & Interrupt Manager
    update_topics_pipeline(user, mem)
    
    # PART 7 — Planner Subsystem
    planner_subsystem(user, mem, categories)
    
    # PART 9 — Symptom Accumulator: build running picture across turns
    _health_mode_active = director_state_pre_run = None  # placeholder; director runs next
    # Pre-check categories for health to accumulate before director runs
    if "health" in categories:
        # Grow active_symptoms with new keywords from this message
        _sym_words = ["headache","vomit","diarrhea","poop","stools","nausea","fever",
                      "dizzy","dizziness","fatigue","pain","stomach","cramps","sick",
                      "unwell","faint","bleeding","swelling","injury","vomiting","chills"]
        l_user = user.lower()
        for _sw in _sym_words:
            if _sw in l_user and _sw not in mem.get("active_symptoms", []):
                mem.setdefault("active_symptoms", []).append(_sw)
        # Escalate health concern level (cap at 10)
        mem["health_concern_level"] = min(10, mem.get("health_concern_level", 0) + 2)
    else:
        # Non-health turn: decay concern level slowly, clear if topic fully changed
        current_mode = mem.get("last_director_mode", "companion")
        if current_mode not in ("health_priority", "health_continuation"):
            if mem.get("health_concern_level", 0) > 0:
                mem["health_concern_level"] = max(0, mem["health_concern_level"] - 1)
            if mem.get("health_concern_level", 0) == 0:
                mem["active_symptoms"] = []

    # PART 9 — Run the unified Conversation Director (Cognitive Controller)
    director_state = conversation_director(user, history, mem, categories)
    print(f"DEBUG DIRECTOR STATE: {director_state}")
    should_search = director_state["should_search"]
    search_query = director_state["search_query"]
    # Track director mode for next-turn emotional continuity
    mem["last_director_mode"] = director_state.get("conversation_mode", "companion")
    if should_search:
        mem["conversation_goal"] = "information retrieval / web search"
        if mem["planner_state"]:
            mem["planner_state"]["primary_goal"] = "information retrieval / web search"
            
    # PART 8 — Emotional Reaction Layer (runs before prompt construction)
    ev = mem.get("emotion_vector", {})
    reaction_directive, micro_reaction = emotional_reaction_layer(user, mem, categories, ev)
    
    behavior_directive = ""
    try:
        from behavior_predictor import get_behavior_predictor
        bp = get_behavior_predictor()
        perception = {}
        perc_path = os.path.join(BASE_DIR, "shared", "perception_state.json")
        if os.path.exists(perc_path):
            with open(perc_path, "r", encoding="utf-8") as pf:
                import json
                perception = json.load(pf)
        behavior_directive = bp.predict_behavior_directive(user, mem, ev, perception)
    except Exception as e:
        print(f"[Conversation] Behavior predictor error: {e}")
        
    if behavior_directive:
        reaction_directive = reaction_directive + "\n" + behavior_directive

    # ── Sleep Subsystem & Human State Machine ──
    human_state = update_human_state(mem, user_input=user)
    sleep_mode = False
    energy_level = 0.70
    try:
        from circadian.circadian_engine import get_state as _get_circ_state
        cs = _get_circ_state()
        if cs:
            energy_level = cs.energy
            sleep_mode = cs.sleep_mode or (energy_level < 0.20)
    except Exception:
        sleep_mode = False

    if sleep_mode or human_state in ("Sleeping", "Deep Sleep", "Dreaming", "Just Woke Up"):
        attempts = mem.get("sleep_wake_attempts", 0) + 1
        mem["sleep_wake_attempts"] = attempts
        
        def _trigger_anim(anim_name):
            try:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                shared_dir = os.path.join(base_dir, "shared")
                os.makedirs(shared_dir, exist_ok=True)
                target_path = os.path.join(shared_dir, "animation_trigger.txt")
                tmp_path = target_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    f.write(anim_name)
                os.replace(tmp_path, target_path)
            except Exception as e:
                print(f"[Conversation] Warning: failed to write animation_trigger.txt: {e}")

        if attempts <= 4:
            _trigger_anim("pillow_ears")
        else:
            _trigger_anim("pillow_throw")

        rel_score = mem.get("relationship", {}).get("score", 30)
        aff_level = mem.get("affection_level", 30.0)

        sleep_directive = (
            f"[INTERNAL STATE: {human_state} (Sleep Mode: {sleep_mode}) | Affection Level: {aff_level:.1f}/100]. "
            "It is late at night / sleep time. "
            "CONTINUOUS HUMAN DIALOGUE DIRECTIVES: "
            "1. Absolutely NO generic greetings ('Hello!', 'Ready to chat!', 'Good morning!'). "
            "2. Do NOT introduce or re-introduce yourself. "
            "3. Do NOT output isolated canned phrases like '...what happened?' or 'I was half asleep...'. "
            "4. Execute the Human Conversational Formula: "
            "[Physical / Sleepy State] + [Direct Acknowledgement & Processing of User's Message] + [Personal Reaction / Relationship Filter] + [Continuation / Question]. "
            "Example: If woken up and user asks 'Will you have coffee with me?', acknowledge the coffee request immediately from your sleepy/groggy state: "
            "'Coffee...? At midnight? I probably shouldn't... but honestly? I'd still come if you asked.'"
        )
        reaction_directive = (reaction_directive + "\n" + sleep_directive).strip()
    else:
        mem["sleep_wake_attempts"] = 0

    # PART 7 — Upgraded Central Cognitive Orchestration (CognitiveOrchestrator)
    try:
        from cognitive_orchestrator import get_cognitive_orchestrator
        orchestrator = get_cognitive_orchestrator()
        orch_pkg = orchestrator.orchestrate_turn_planning(
            user_text=user,
            categories=categories,
            mem=mem,
            perception_state=perception_state
        )
        plan = orch_pkg["plan"]
        aff_res = orch_pkg["affection_state"]
        lon_res = orch_pkg["loneliness_state"]
        print(f"[CognitiveOrchestrator] Topic: '{plan['current_topic']}' | Tone: '{plan['tone']}' | Depth: '{plan['depth']}' | Stage: '{aff_res['stage_label']}'")

    except Exception as _subsys_err:
        print(f"[CognitiveSubsystems] Integration fallback warning: {_subsys_err}")
        update_relationship(mem, categories)
        update_emotion_vector(mem, categories, history)
        update_mood(mem)

    # PART 3 — Determine dynamic limits and temperature
    limits = get_model_limits()
    temperature = get_adaptive_temp(categories, user)
    # Boost temperature slightly for emotional/intimate moments for more spontaneous replies
    if any(c in categories for c in ["intimacy", "vulnerable", "comfort", "flirting"]):
        temperature = min(1.0, temperature + 0.08)
    
    t_pre = time.time() - t_start
    print(f"PART 7 Subsystem Preprocessing Time: {t_pre*1000:.2f}ms")

    history.append("You: " + user)
    
    # PART 6 — Incremental summary manager triggered on context overflow
    max_hist = limits["max_history"]
    if len(history) > max_hist + 4:
        discarded_turns = history[:-(max_hist + 4)]
        update_summary_incremental(mem, discarded_turns)
        history = history[-(max_hist + 4):]
    else:
        history = compress(history, max_hist + 4)

    # DuckDuckGo search — autonomous LLM-driven decision with KnowledgeRouter capability detection
    search_context = ""
    if should_search:
        print(f"Autonomous Search triggered: query='{search_query}' (user said: '{user}')")
        print(f"DEBUG: get_knowledge_router is {get_knowledge_router}")
        if get_knowledge_router is not None:
            kr = get_knowledge_router()
            search_context = kr.route_knowledge_query(search_query, search_duckduckgo)
            if not search_context and search_query != user:
                search_context = kr.route_knowledge_query(user, search_duckduckgo)
        else:
            search_context = search_duckduckgo(search_query)
        if not search_context and search_query != user:
                search_context = search_duckduckgo(user)

    if not search_context and perception_state:
        _music = perception_state.get("audio_music_title", "")
        _app = perception_state.get("active_window_title", "") or perception_state.get("current_app_type", "")
        if _music and len(_music) > 3 and not any(x in _music.lower() for x in ("unknown", "silence")):
            print(f"[DuckDuckGo Perception] Autonomous search for music title: '{_music}'")
            search_context = search_duckduckgo(_music)
        elif _app and any(x in _app.lower() for x in ("youtube", "nightcore", "spotify", "edge", "chrome", "firefox")):
            clean_q = _app.split(" - ")[0].strip()
            if len(clean_q) > 4 and not any(x in clean_q.lower() for x in ("vivy ai", "localhost", "127.0.0.1")):
                print(f"[DuckDuckGo Perception] Autonomous search for app context: '{clean_q}'")
                search_context = search_duckduckgo(clean_q)

    # Read current emotion state from classifier output
    current_emotion = _read_emotion()

    # PART 8b — Neural Learning Prediction (Level 8)
    try:
        from neural.prediction_engine import get_prediction_engine
        import uuid
        context_id = mem.get("active_trace_id", str(uuid.uuid4()))
        pe = get_prediction_engine()
        # We predict perfect outcomes for the chosen strategy
        expected = {
            "task_success": 1.0,
            "user_feedback": 1.0,
            "efficiency": 0.8
        }
        pe.predict(context_id, expected)
        # Store context_id for the outcome publisher
        mem["current_turn_id"] = context_id
    except Exception as e:
        print(f"[Neural Fabric] Prediction error: {e}")

    # PART 3 — Orchestrate LLM with Validation and Regeneration
    reply = ""
    best_candidate = ""
    best_candidate_score = -1.0
    
    # We allow up to 2 attempts: Candidate Generation & Regeneration
    for attempt in range(1, 3):
        # On attempt 2, adjust temperature to force variation
        run_temp = temperature
        if attempt == 2:
            run_temp = min(1.2, max(0.1, temperature + (0.15 if temperature < 0.8 else -0.15)))
            print(f"Attempt 2: Adjusting temperature from {temperature} to {run_temp}")
            
        try:
            # Scale max_tokens dynamically based on planned complexity strategy
            strategy_plan = mem.get("strategy_plan", {})
            strategy = strategy_plan.get("strategy", "medium")
            max_tokens_map = {
                "tiny":       60,
                "short":      150,
                "medium":     350,
                "long":      600,
                "empathy":   400,
                "advice":    500,
                "humor":     300,
                "story":     650,
                "tutorial":  800,
                "perception": 600,   # legacy support
                "perception_highlight": 100, # short/precise highlight answers
                "perception_short": 200,     # short confirmation replies
                "perception_detailed": 600,  # detailed descriptions
            }
            run_max_tokens = max_tokens_map.get(strategy, 350)

            # ── Perception query token budget override ──
            # When the user asks "what do you see / hear / what's highlighted",
            # provide a generous token budget so the response is never cut off mid-sentence.
            if strategy == "perception_highlight":
                pass
            elif _is_perception_query:
                run_max_tokens = max(run_max_tokens, 500)
            elif categories and ("screen" in categories or "audio_query" in categories):
                run_max_tokens = max(run_max_tokens, 450)
            
            if stream:
                out = llm(
                    build(mem, history, user, search_context, current_emotion, categories, reaction_directive, director_state, screen_context, perception_context, perception_state, wants_vision=wants_vision, wants_audio=wants_audio),
                    max_tokens=run_max_tokens,
                    temperature=run_temp,
                    stop=["<|im_end|>", "<|im_start|>", "<|endoftext|>", "\nYou:", "\nVivy:", "<|user|>", "<|system|>"],
                    stream=True
                )
                def _stream_generator():
                    raw_acc = ""
                    in_think_block = False
                    buffer = ""
                    
                    if micro_reaction:
                        yield {'type': 'token', 'text': micro_reaction + " "}
                        
                    for chunk in out:
                        if response_context and pipeline_manager.is_cancelled(response_context):
                            break
                        tok = chunk["choices"][0]["text"]
                        raw_acc += tok
                        buffer += tok
                        
                        if not in_think_block:
                            tag_idx = buffer.find("<think")
                            if tag_idx != -1:
                                if buffer.find("<think>") != -1:
                                    if tag_idx > 0:
                                        yield {'type': 'token', 'text': buffer[:tag_idx]}
                                    in_think_block = True
                                    buffer = buffer[buffer.find("<think>")+7:]
                                else:
                                    if tag_idx > 0:
                                        yield {'type': 'token', 'text': buffer[:tag_idx]}
                                        buffer = buffer[tag_idx:]
                            else:
                                yield {'type': 'token', 'text': buffer}
                                buffer = ""
                        else:
                            end_idx = buffer.find("</think>")
                            if end_idx != -1:
                                in_think_block = False
                                buffer = buffer[end_idx+8:]
                            else:
                                if len(buffer) > 8:
                                    buffer = buffer[-8:]
                    
                    if buffer and not in_think_block and "<think" not in buffer:
                        yield {'type': 'token', 'text': buffer}
                        
                    if response_context and pipeline_manager.is_cancelled(response_context):
                        return
                        
                    # End of stream, finalize reply
                    t_clean = clean(raw_acc, user, mem)
                    if not t_clean and raw_acc:
                        raw_clean = _THINK_BLOCK_RE.sub("", raw_acc).strip()
                        raw_clean = _THINK_TAG_RE.sub("", raw_clean).strip()
                        t_clean = clean(raw_clean, user, mem)
                        if not t_clean: t_clean = raw_clean
                            
                    reply = t_clean
                    if micro_reaction and not reply.lower().startswith(micro_reaction.lower().strip("—. ")):
                        reply = micro_reaction + " " + reply
                        
                    p_state = mem.get("planner_state", {})
                    s_plan = mem.get("strategy_plan", {})
                    if (p_state.get("ask_question") or s_plan.get("ask_question")) and "?" not in reply:
                        reply = generate_followup_question(user, reply, mem, categories)
                        
                    reply = add_emoji(reply, mem.get("tone", "neutral"))
                    history.append("Vivy: " + reply)
                    mem["last_reply"] = reply
                    
                    try:
                        self_evolution_reflection(user, reply, mem, perception_context=perception_context, perception_state=perception_state)
                        self_reflection(user, reply, mem)
                    except Exception as e: print("Reflection error:", e)
                    
                    save(mem)
                    yield {'type': 'final_state', 'history': history, 'reply': reply}
                
                return _stream_generator()
            else:
                out = llm(
                    build(mem, history, user, search_context, current_emotion, categories, reaction_directive, director_state, screen_context, perception_context, perception_state, wants_vision=wants_vision, wants_audio=wants_audio),
                    max_tokens=run_max_tokens,
                    temperature=run_temp,
                    stop=["<|im_end|>", "<|im_start|>", "<|endoftext|>", "\nYou:", "\nVivy:", "<|user|>", "<|system|>"]
                )
                raw = out["choices"][0]["text"]
        except Exception as le:
            print(f"LLM call exception on attempt {attempt}: {le}")
            raw = ""
            
        t_clean = clean(raw, user, mem)
        if not t_clean and raw:
            # Fallback cleanup logic to strip tags if clean was too aggressive
            raw_clean = _THINK_BLOCK_RE.sub("", raw).strip()
            raw_clean = _THINK_TAG_RE.sub("", raw_clean).strip()
            t_clean = clean(raw_clean, user, mem)
            if not t_clean:
                lines = [l.strip() for l in raw_clean.split("\n") if l.strip()]
                # Root-cause fix: retain complete multi-line responses under 400 chars rather than
                # severing at the first line break (e.g. after interjections or Japanese commas).
                candidate = " ".join(lines) if (lines and len(" ".join(lines)) < 400) else (lines[0] if lines else "")
                # Strip any surviving think tags from the raw line candidate
                candidate = _THINK_TAG_RE.sub("", candidate).strip()
                # Discard if result is empty, contains XML/HTML tags, or is a single English token
                if candidate and "<" not in candidate and ">" not in candidate and (len(candidate.split()) >= 2 or any(ord(c) > 127 for c in candidate)):
                    t_clean = candidate
                else:
                    t_clean = ""
                
        if t_clean:
            # Evaluate using PART 5 Response Intelligence Engine (RIE)
            score, is_valid = score_response_rie(t_clean, user, mem, categories, history, perception_state=perception_state)
            print(f"Attempt {attempt} candidate: '{t_clean}' | RIE Score: {score} | Valid: {is_valid}")
            
            # Grounding and memory override check
            if is_valid:
                grounded_valid, ground_reason = validate_perception_grounding(t_clean, user, mem, perception_state or {}, t_start)
                if not grounded_valid:
                    print(f"Self-Validation Loop rejected candidate on attempt {attempt}: {ground_reason}. Discarding response.")
                    is_valid = False
                    # On attempt 1, trigger fresh perception state reload for attempt 2
                    if attempt == 1:
                        try:
                            time.sleep(0.3)  # Wait for next frame to arrive
                            from perception.perception_manager import get_reader
                            perception_state = get_reader().load_state()
                            wants_vision, wants_audio = classify_perception_modality(user)
                            perception_state["_grounding_context"] = get_reader().build_grounding_context(
                                screen_context, wants_vision=wants_vision, wants_audio=wants_audio
                            )
                        except Exception as _err:
                            print(f"[conversation.py] Silenced exception: {_err}")
            
            # Keep track of the highest-scoring candidate as our recovery safety
            if score > best_candidate_score:
                best_candidate_score = score
                best_candidate = t_clean
                
            if is_valid:
                reply = t_clean
                print(f"Attempt {attempt} passed all RIE checklist checks.")
                break
        else:
            print(f"Attempt {attempt} returned empty cleaned text.")
            
    # Fallback resolution if both attempts failed to yield a valid response
    if not reply:
        if best_candidate and len(best_candidate.strip()) >= 5 and not is_reasoning_sentence(best_candidate):
            print(f"Both attempts failed strict RIE validation, but adopting best candidate (Score: {best_candidate_score}): '{best_candidate}' instead of scripted fallback.")
            reply = best_candidate
        else:
            print("Both attempts failed RIE checks or contained developer log reasoning. Returning relational companion fallback.")
            reply = _pick_fallback(director_state, categories, user_query=user, perception_state=perception_state, wants_vision=wants_vision, wants_audio=wants_audio, mem=mem)
            try:
                from agi.bus.event_bus import get_event_bus
                get_event_bus().publish("FALLBACK_ACTIVATED", {"reason": "RIE validation failed or perception missing", "reply": reply})
            except Exception as e:
                pass

    # AGI Meta-Cognition Reflexive Response Verification (Reason -> Critique -> Improve -> Verify)
    try:
        from agi.cognitive_core import get_cognitive_core
        reply = get_cognitive_core().verify_and_refine_response(
            user_text=user,
            candidate_reply=reply,
            plan=mem.get("planner_decision", {}),
            mem=mem
        )
    except Exception as _mc_err:
        print(f"[AGI MetaCognition] Verification warning: {_mc_err}")

    # Relationship Continuity Engine (Relationship Response Layer)
    try:
        from affection.continuity_engine import get_continuity_engine
        reply = get_continuity_engine().evaluate_and_adapt(
            draft_reply=reply,
            user_input=user,
            mem=mem,
            history=history,
            categories=categories
        )
    except Exception as _rc_err:
        print(f"[RelationshipContinuityEngine] Warning (non-fatal): {_rc_err}")

    # Developer Diagnostic Mode Hook (Phase 6 Prompt Inspector)
    try:
        from developer_diagnostic_manager import get_developer_diagnostic_manager
        ddm = get_developer_diagnostic_manager()
        if ddm.is_enabled():
            p_st = perception_state or {}
            ddm.record_prompt_trace(
                user_query=user,
                camera_observations={
                    "camera_active": p_st.get("camera_active", False),
                    "face_count": p_st.get("face_count", 0),
                    "object_count": p_st.get("object_count", 0),
                    "gaze": p_st.get("gaze_direction", "unknown"),
                },
                vision_model_output={
                    "caption": p_st.get("vision_latest_caption", ""),
                    "ocr": p_st.get("last_ocr_text", "")[:100],
                },
                context_builder_output=str(perception_context or "")[:200],
                final_prompt_sent=str(user),
                raw_llm_response=str(raw if 'raw' in locals() else ""),
                filtered_response=str(t_clean if 't_clean' in locals() else ""),
                final_spoken_response=reply,
                fallback_triggered=bool(not reply or reply in _FALLBACK_REPLIES or reply in _FALLBACK_HEALTH or reply in _FALLBACK_RECIPE),
                fallback_reason="RIE validation fallback" if (not reply or reply in _FALLBACK_REPLIES) else None
            )
    except Exception as _err:
        print(f"[conversation.py] Silenced exception: {_err}")

    # PART 8 — Apply micro-reaction prefix if one was generated
    # Only prepend if the reply doesn't already naturally open that way
    if micro_reaction:
        # Check if prepending would cause a repeated opening, if so skip it
        test_reply = micro_reaction + " " + reply
    if micro_reaction and not reply.lower().startswith(micro_reaction.lower().strip("—. ")):
        reply = micro_reaction + " " + reply

    # Phase 7 — Follow-Up Question Engine
    p_state = mem.get("planner_state", {})
    s_plan = mem.get("strategy_plan", {})
    if (p_state.get("ask_question") or s_plan.get("ask_question")) and "?" not in reply:
        reply = generate_followup_question(user, reply, mem, categories)

    reply = add_emoji(reply, mem["tone"])
    history.append("Vivy: " + reply)
    mem["last_reply"] = reply
    
    # Session isolation & Memory consolidation hook
    if get_session_manager is not None:
        try:
            sess = get_session_manager().get_active_session()
            sess.add_user_message(user)
            sess.add_assistant_reply(reply, emotion=detect_emotion(reply) if 'detect_emotion' in globals() else "neutral")
            if get_memory_orchestrator is not None:
                get_memory_orchestrator().consolidate_memory(sess.session_messages)
        except Exception as _sess_err:
            print(f"[conversation] Session logging notice: {_sess_err}")
    
    # PART 6 — Question & Promise Tracker
    update_questions_promises(user, reply, mem)
    
    # PART 2 — Track reply opening for repetition detection
    _track_opening(reply, mem)
    
    # Run cognitive reflection and evolution to consolidate memories
    self_evolution_reflection(user, reply, mem, perception_context=perception_context, perception_state=perception_state)
    self_reflection(user, reply, mem)
    
    # Run post-response cognitive orchestration evaluation
    try:
        from cognitive_orchestrator import get_cognitive_orchestrator
        get_cognitive_orchestrator().orchestrate_post_response(
            user_text=user,
            reply_text=reply,
            plan=mem.get("planner_decision", {}),
            mem=mem,
            categories=categories,
            search_used=should_search,
            t_start=t_start
        )
    except Exception as _post_err:
        print(f"[CognitiveOrchestrator] Post-response evaluation warning: {_post_err}")

    # ── ML Continuous Learning (Experience Replay) ──
    if _experience_replay is not None:
        try:
            # Assuming engagement is high if user input was long, otherwise neutral reward proxy
            reward_proxy = 1.0 if len(user) > 20 else 0.5
            _experience_replay.log_interaction(
                user_input=user,
                ai_response=reply,
                context_state={"topic": mem.get("current_topic")},
                emotion_state=mem.get("mood", "neutral"),
                reward_proxy=reward_proxy
            )
        except Exception as _replay_err:
            print(f"[ExperienceReplay] Logging warning: {_replay_err}")

    # ── Unified Cognitive Event Bus ──
    try:
        from agi.bus.event_bus import get_event_bus
        bus = get_event_bus()
        bus.publish("PERCEPTION_UPDATE", {"user_addressed_ai": True, "perception_state": perception_state})
        bus.publish("COGNITION_OUTCOME", {
            "id": mem.get("current_turn_id", str(t_start)),
            "user_input": user,
            "reply": reply if 'reply' in locals() else "",
            "topic": mem.get("current_topic"),
            "mood": mem.get("mood", "neutral"),
            "task_success": 1.0 if 'reply' in locals() and reply else 0.0,
            "efficiency": 0.8
        })
        
        # USER_FEEDBACK will trigger the reward engine and novelty detector
        bus.publish("USER_FEEDBACK", {
            "score": 1.0 if len(user) > 10 else 0.5,
            "task_success": 1.0 if 'reply' in locals() and reply else 0.0,
            "emotional_outcome": 0.5, # Placeholder for real emotional analysis
            "factual_accuracy": 0.8,
            "efficiency": 0.8,
            "relationship_consistency": 0.9,
            "novelty": 0.5,
            "surprise": 0.5,
            "importance": 0.5,
            "recurrence": 1.0,
            "user_state": {},
            "emotion_state": {"mood": mem.get("mood", "neutral")},
            "perception_state": perception_state,
            "goal": mem.get("conversation_goal", ""),
            "action": reply if 'reply' in locals() else "",
            "tool_usage": [],
            "response_strategy": mem.get("strategy_plan", {}).get("strategy", ""),
            "prediction": {},
            "outcome": {"success": True},
            "confidence": 0.9
        })
    except Exception as e:
        print(f"[EventBus] Publish error: {e}")

    save(mem)
    if stream:
        def early_gen():
            yield {'type': 'token', 'text': reply}
            yield {'type': 'final_state', 'history': history, 'reply': reply}
        return early_gen()
    return reply, history

if __name__ == "__main__":
    history = []
    mem = load()

    first = greeting(mem)
    print("Vivy:", first)
    history.append("Vivy: " + first)

    while True:
        user = input("You: ").strip()
        if user.lower() in ["exit", "quit"]:
            break

        reply, history = generate_reply_internal(user, history, mem)
        print("Vivy:", reply)
