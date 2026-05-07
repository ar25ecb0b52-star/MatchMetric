# backend/app.py
# ─────────────────────────────────────────────────────────────
# Flask backend — updated for:
#   - JD file upload (PDF / DOCX / TXT)
#   - Multiple resume matching in one request
# ─────────────────────────────────────────────────────────────

import os
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS

from resume_parser import extract_text, get_file_info, get_word_count
from matcher import compute_match

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER     = os.path.join(os.path.dirname(__file__), "..", "uploads")
ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"]         = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"]    = 20 * 1024 * 1024   # 20 MB


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ── Routes ────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "Resume Matcher API is live ✅"})


@app.route("/upload-resume", methods=["POST"])
def upload_resume():
    """Upload a single resume file and return extracted text."""
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": f"Unsupported file type. Allowed: {ALLOWED_EXTENSIONS}"}), 400

    save_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
    file.save(save_path)

    try:
        extracted_text = extract_text(save_path)
        file_info      = get_file_info(save_path)
        word_count     = get_word_count(extracted_text)
    except (FileNotFoundError, ValueError) as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        logger.exception("Extraction error")
        return jsonify({"error": f"Extraction failed: {str(e)}"}), 500

    return jsonify({
        "filename":       file_info["filename"],
        "extension":      file_info["extension"],
        "size_kb":        file_info["size_kb"],
        "word_count":     word_count,
        "extracted_text": extracted_text,
    })


@app.route("/upload-jd", methods=["POST"])
def upload_jd():
    """Upload a JD file (PDF / DOCX / TXT) and return extracted text."""
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": f"Unsupported file type. Allowed: {ALLOWED_EXTENSIONS}"}), 400

    save_path = os.path.join(app.config["UPLOAD_FOLDER"], "jd_" + file.filename)
    file.save(save_path)

    try:
        extracted_text = extract_text(save_path)
        file_info      = get_file_info(save_path)
        word_count     = get_word_count(extracted_text)
    except Exception as e:
        logger.exception("JD extraction error")
        return jsonify({"error": f"Extraction failed: {str(e)}"}), 500

    return jsonify({
        "filename":       file_info["filename"],
        "extension":      file_info["extension"],
        "size_kb":        file_info["size_kb"],
        "word_count":     word_count,
        "extracted_text": extracted_text,
    })


@app.route("/match", methods=["POST"])
def match():
    """
    Single resume match.
    Body: { "resume_text": "...", "jd_text": "..." }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    resume_text = data.get("resume_text", "").strip()
    jd_text     = data.get("jd_text",     "").strip()

    if not resume_text or not jd_text:
        return jsonify({"error": "Both resume_text and jd_text are required"}), 400

    try:
        return jsonify(compute_match(resume_text, jd_text))
    except Exception as e:
        logger.exception("Match error")
        return jsonify({"error": f"Matching failed: {str(e)}"}), 500


@app.route("/match-multiple", methods=["POST"])
def match_multiple():
    """
    Match multiple resumes against one JD.
    Body: {
        "jd_text": "...",
        "resumes": [
            { "filename": "alice.pdf", "text": "..." },
            { "filename": "bob.pdf",   "text": "..." },
            ...
        ]
    }
    Returns list of results sorted by overall_score descending.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    jd_text = data.get("jd_text", "").strip()
    resumes = data.get("resumes", [])

    if not jd_text:
        return jsonify({"error": "jd_text is required"}), 400
    if not resumes:
        return jsonify({"error": "resumes list is empty"}), 400

    results = []
    for r in resumes:
        filename    = r.get("filename", "unknown")
        resume_text = r.get("text", "").strip()
        if not resume_text:
            results.append({
                "filename": filename,
                "error":    "No text extracted from this file",
                "overall_score": 0.0,
            })
            continue
        try:
            result             = compute_match(resume_text, jd_text)
            result["filename"] = filename
            results.append(result)
        except Exception as e:
            logger.exception(f"Match error for {filename}")
            results.append({
                "filename":      filename,
                "error":         str(e),
                "overall_score": 0.0,
            })

    # Sort by overall score descending
    results.sort(key=lambda x: x.get("overall_score", 0), reverse=True)
    return jsonify({"results": results, "total": len(results)})


# ── Run ───────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🚀  Starting Resume Matcher API on http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
