# backend/matcher.py
# ─────────────────────────────────────────────────────────────
# Phase 3 (updated) — Full matching engine with improved semantic analysis.
# Three scoring layers:
#   1. Keyword Match        (30% weight)
#   2. TF-IDF Cosine        (50% weight) — pure Python fallback
#   3. Semantic Similarity  (20% weight) — improved word-vector approach
# ─────────────────────────────────────────────────────────────

import re
import math
import logging
from collections import Counter

logger = logging.getLogger(__name__)

# ── Load spaCy once at startup ────────────────────────────────
_NLP = None
try:
    import spacy
    _NLP = spacy.load("en_core_web_sm")
    logger.info("spaCy loaded.")
except Exception:
    logger.info("spaCy unavailable — using keyword scan fallback.")

# ── Tech keyword dictionary ───────────────────────────────────
TECH_KEYWORDS = {
    "python","java","javascript","typescript","c++","c#","ruby","go","rust",
    "kotlin","swift","bash","sql","r","scala","matlab","php","html","css",
    "flask","fastapi","django","spring","express","react","angular","vue",
    "nodejs","sqlalchemy","celery","pandas","numpy","scipy","matplotlib",
    "tensorflow","keras","pytorch","scikit-learn","sklearn","spacy","nltk",
    "opencv","pyspark",
    "postgresql","mysql","sqlite","mongodb","redis","cassandra",
    "elasticsearch","dynamodb","oracle","firestore",
    "aws","gcp","azure","ec2","s3","lambda","docker","kubernetes","terraform",
    "ansible","jenkins","github actions","ci/cd","circleci","heroku",
    "rest","restful","api","microservices","graphql","grpc","websocket",
    "machine learning","deep learning","nlp","computer vision","data pipeline",
    "etl","agile","scrum","tdd","oop",
    "git","jira","postman","swagger","linux","unix",
    "kafka","rabbitmq","airflow","spark","hadoop","pytest",
}

STOP_WORDS = {
    "a","an","the","and","or","but","in","on","at","to","for","of","with",
    "by","from","as","is","was","are","were","be","been","being","have",
    "has","had","do","does","did","will","would","could","should","may",
    "might","shall","can","need","this","that","these","those","i","we",
    "you","he","she","it","they","me","us","him","her","them","my","our",
    "your","his","its","their","what","which","who","how","when","where",
    "not","no","nor","so","yet","both","either","about","above","after",
    "before","between","into","through","during","including","without",
    "per","than","then","too","very","just","more","also","well","such",
    "only","other","same","each","all","any","few","most","some",
}

# ── Section header patterns for section-aware scoring ─────────
SKILL_SECTION_PATTERNS = re.compile(
    r"(skills?|technologies|tech stack|tools?|expertise|competencies|qualifications)",
    re.IGNORECASE
)
EXPERIENCE_SECTION_PATTERNS = re.compile(
    r"(experience|employment|work history|professional background|career)",
    re.IGNORECASE
)


# ══════════════════════════════════════════════════════════════
#  Public API
# ══════════════════════════════════════════════════════════════

def compute_match(resume_text: str, jd_text: str) -> dict:
    resume_clean = _preprocess(resume_text)
    jd_clean     = _preprocess(jd_text)

    keyword_result = _keyword_match(resume_clean, jd_clean)
    tfidf_score    = _tfidf_cosine_similarity(resume_clean, jd_clean)
    semantic_score = _semantic_similarity(resume_text, jd_text)   # raw text for section awareness

    overall = min(
        keyword_result["score"] * 0.30
        + tfidf_score           * 0.50
        + semantic_score        * 0.20,
        100.0
    )

    return {
        "overall_score":    round(overall, 2),
        "keyword_score":    round(keyword_result["score"], 2),
        "tfidf_score":      round(tfidf_score, 2),
        "semantic_score":   round(semantic_score, 2),
        "matched_keywords": keyword_result["matched"],
        "missing_keywords": keyword_result["missing"],
    }


# ══════════════════════════════════════════════════════════════
#  Pre-processing
# ══════════════════════════════════════════════════════════════

def _preprocess(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s\+\#]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _tokenize(text: str) -> list:
    return [w for w in text.split() if w not in STOP_WORDS and len(w) > 2]


# ══════════════════════════════════════════════════════════════
#  Layer 1 — Keyword Matching
# ══════════════════════════════════════════════════════════════

def _keyword_match(resume_text: str, jd_text: str) -> dict:
    jd_keywords = _extract_keywords(jd_text)
    if not jd_keywords:
        return {"score": 0.0, "matched": [], "missing": []}

    matched, missing = [], []
    for kw in jd_keywords:
        pattern = r"\b" + re.escape(kw) + r"\b"
        if re.search(pattern, resume_text):
            matched.append(kw)
        else:
            missing.append(kw)

    score = len(matched) / len(jd_keywords) * 100
    return {"score": round(score, 2), "matched": sorted(matched), "missing": sorted(missing)}


def _extract_keywords(text: str) -> list:
    keywords = set()
    if _NLP is not None:
        try:
            doc = _NLP(text[:100000])
            for chunk in doc.noun_chunks:
                kw = chunk.text.strip().lower()
                if len(kw) > 2 and not _is_stopword(kw):
                    keywords.add(kw)
            for ent in doc.ents:
                if ent.label_ in ("ORG", "PRODUCT", "GPE", "LANGUAGE"):
                    keywords.add(ent.text.strip().lower())
        except Exception as e:
            logger.warning(f"spaCy error: {e}")
    keywords |= _scan_tech_keywords(text)
    return list(keywords)


def _scan_tech_keywords(text: str) -> set:
    return {kw for kw in TECH_KEYWORDS if re.search(r"\b" + re.escape(kw) + r"\b", text)}


def _is_stopword(text: str) -> bool:
    STOPS = {
        "experience","knowledge","understanding","ability","skills","skill",
        "years","year","role","team","work","working","strong","good",
        "excellent","degree","bachelor","master","etc","including","related",
    }
    return text in STOPS or (len(text.split()) == 1 and len(text) <= 2)


# ══════════════════════════════════════════════════════════════
#  Layer 2 — TF-IDF Cosine Similarity
# ══════════════════════════════════════════════════════════════

def _tfidf_cosine_similarity(resume_text: str, jd_text: str) -> float:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity as sk_cosine
        vec    = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
        matrix = vec.fit_transform([resume_text, jd_text])
        return round(float(sk_cosine(matrix[0], matrix[1])[0][0]) * 100, 2)
    except Exception:
        pass

    # Pure Python fallback
    try:
        resume_tokens = _tokenize(resume_text)
        jd_tokens     = _tokenize(jd_text)
        if not resume_tokens or not jd_tokens:
            return 0.0

        vocab     = list(set(resume_tokens) | set(jd_tokens))
        docs      = [set(resume_tokens), set(jd_tokens)]
        N         = 2

        def build_vector(tokens):
            tf_map = Counter(tokens)
            total  = len(tokens)
            vec    = []
            for w in vocab:
                tf_val  = tf_map.get(w, 0) / total
                df      = sum(1 for d in docs if w in d)
                idf_val = math.log((N + 1) / (df + 1)) + 1
                vec.append(tf_val * idf_val)
            return vec

        return round(_cosine(build_vector(resume_tokens), build_vector(jd_tokens)) * 100, 2)
    except Exception as e:
        logger.error(f"TF-IDF error: {e}")
        return 0.0


# ══════════════════════════════════════════════════════════════
#  Layer 3 — Improved Semantic Similarity
# ══════════════════════════════════════════════════════════════

def _semantic_similarity(resume_text: str, jd_text: str) -> float:
    """
    Improved semantic analysis using section-aware scoring:
    1. Extracts skills/experience sections separately and weights them higher.
    2. Uses sentence-transformers if available.
    3. Falls back to TF-IDF weighted word-vector overlap.
    4. Last resort: character n-gram Jaccard.
    """
    # ── Extract high-value sections ───────────────────
    resume_skills_section = _extract_section(resume_text, SKILL_SECTION_PATTERNS)
    resume_exp_section    = _extract_section(resume_text, EXPERIENCE_SECTION_PATTERNS)
    jd_req_section        = _extract_section(jd_text,     SKILL_SECTION_PATTERNS)

    # Build a weighted representation:
    # Skills/requirements sections count 3x, full text counts 1x
    resume_weighted = " ".join([
        resume_text,
        resume_skills_section * 3,
        resume_exp_section    * 2,
    ])
    jd_weighted = " ".join([
        jd_text,
        jd_req_section * 3,
    ])

    # ── Try sentence-transformers ──────────────────────
    try:
        from sentence_transformers import SentenceTransformer, util  # type: ignore
        model  = SentenceTransformer("all-MiniLM-L6-v2")
        emb1   = model.encode(" ".join(resume_weighted.split()[:512]), convert_to_tensor=True)
        emb2   = model.encode(" ".join(jd_weighted.split()[:512]),     convert_to_tensor=True)
        return round(float(util.cos_sim(emb1, emb2).item()) * 100, 2)
    except ImportError:
        pass
    except Exception as e:
        logger.error(f"Sentence-transformers error: {e}")

    # ── TF-IDF word-vector overlap (improved fallback) ─
    try:
        score = _word_vector_similarity(
            _preprocess(resume_weighted),
            _preprocess(jd_weighted)
        )
        return round(score * 100, 2)
    except Exception as e:
        logger.error(f"Word-vector semantic error: {e}")

    # ── Last resort: character n-gram Jaccard ──────────
    try:
        def char_ngrams(text: str, n: int = 4) -> set:
            return {text[i:i+n] for i in range(len(text) - n + 1)}
        r = char_ngrams(_preprocess(resume_text))
        j = char_ngrams(_preprocess(jd_text))
        union = len(r | j)
        return round(len(r & j) / union * 100, 2) if union else 0.0
    except Exception as e:
        logger.error(f"Char n-gram error: {e}")
        return 0.0


def _word_vector_similarity(text_a: str, text_b: str) -> float:
    """
    Build a TF-IDF weighted average word vector for each document
    and compute cosine similarity between them.
    This captures semantic proximity better than raw word overlap.
    """
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)

    if not tokens_a or not tokens_b:
        return 0.0

    all_tokens = tokens_a + tokens_b
    vocab      = list(set(all_tokens))
    vocab_idx  = {w: i for i, w in enumerate(vocab)}
    N          = len(vocab)
    docs       = [set(tokens_a), set(tokens_b)]

    def idf(word):
        df = sum(1 for d in docs if word in d)
        return math.log((3) / (df + 1)) + 1

    def weighted_vector(tokens):
        tf_map = Counter(tokens)
        total  = len(tokens)
        vec    = [0.0] * N
        for w, cnt in tf_map.items():
            if w in vocab_idx:
                tf_val  = cnt / total
                vec[vocab_idx[w]] = tf_val * idf(w)
        return vec

    return _cosine(weighted_vector(tokens_a), weighted_vector(tokens_b))


def _extract_section(text: str, pattern: re.Pattern) -> str:
    """
    Extract text from a specific section of the document.
    Looks for section headers matching the pattern and grabs
    the following ~300 words.
    """
    lines   = text.split("\n")
    result  = []
    capture = False
    count   = 0

    for line in lines:
        if pattern.search(line):
            capture = True
            count   = 0
            continue
        if capture:
            words = line.split()
            result.extend(words)
            count += len(words)
            if count >= 300:   # stop after ~300 words per section
                capture = False

    return " ".join(result)


# ══════════════════════════════════════════════════════════════
#  Shared Math Utility
# ══════════════════════════════════════════════════════════════

def _cosine(vec_a: list, vec_b: list) -> float:
    dot   = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a * a for a in vec_a))
    mag_b = math.sqrt(sum(b * b for b in vec_b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)
