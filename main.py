# main.py
import os
import uuid
import shutil
import zipfile
import subprocess
from threading import Thread, Lock
from typing import Dict, Optional, List

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

# -----------------------------
# Настройки
# -----------------------------
ALLOWED_ORIGINS = [
    "https://eyacademycca.com",
    "https://www.eyacademycca.com",
    "https://tilda.cc",
    "https://static.tildacdn.info",
    "*"  # при необходимости сузьте список
]

OUTPUT_DIR = "output"
TEMPLATE_PPTX = "template.pptx"  # ожидается рядом с приложением

os.makedirs(OUTPUT_DIR, exist_ok=True)

app = FastAPI(title="Kuvertki Generator", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Примитивное хранилище прогресса
# -----------------------------
PROGRESS_LOCK = Lock()
PROGRESS: Dict[str, dict] = {}       # {job_id: {"p": int, "msg": str, "file": Optional[str]}}

def setp(job_id: str, p: int, msg: str):
    with PROGRESS_LOCK:
        PROGRESS[job_id] = {
            "p": p,
            "msg": msg,
            "file": PROGRESS.get(job_id, {}).get("file")
        }

def setfile(job_id: str, file_path: str):
    with PROGRESS_LOCK:
        data = PROGRESS.get(job_id, {})
        data["file"] = file_path
        PROGRESS[job_id] = data

def get_state(job_id: str):
    with PROGRESS_LOCK:
        return PROGRESS.get(job_id, {"p": -1, "msg": "Не найдено", "file": None})

# -----------------------------
# ВАША ОСНОВНАЯ ЛОГИКА ГЕНЕРАЦИИ
# -----------------------------
def generate_pdf(names: List[str], job_id: Optional[str] = None) -> str:
    """
    Возвращает путь к готовому PDF в OUTPUT_DIR.
    Здесь должен быть ваш существующий конвейер:
      - распаковка template.pptx
      - подстановка имён/слайдов
      - сборка pptx
      - конвертация в PDF через LibreOffice
    Маркеры прогресса выставляйте вызовами setp(job_id, %, "сообщение").
    """
    uid = uuid.uuid4().hex
    work_dir = f"tmp_{uid}"
    os.makedirs(work_dir, exist_ok=True)

    try:
        if job_id:
            setp(job_id, 5, "Распаковка шаблона...")

        # --- пример распаковки PPTX ---
        if not os.path.exists(TEMPLATE_PPTX):
            raise FileNotFoundError("Не найден template.pptx рядом с приложением")
        with zipfile.ZipFile(TEMPLATE_PPTX, 'r') as z:
            z.extractall(work_dir)

        # TODO: СФОРМИРУЙТЕ НУЖНОЕ КОЛ-ВО СЛАЙДОВ И ПОДСТАНОВКИ
        # ВАШ КОД ИЗ /generate:
        # - правка XML в work_dir/ppt/slides/*.xml
        # - дублирование нужных слайдов
        # - замены текста на имена (жирный/позиционирование и т.д.)
        # Вставляйте маркеры прогресса как ниже:
        if job_id:
            setp(job_id, 30, "Формирование слайдов...")

        # --- сборка pptx обратно ---
        if job_id:
            setp(job_id, 55, "Сборка PPTX...")
        rebuilt_zip = os.path.join(OUTPUT_DIR, f"{uid}.pptx")
        shutil.make_archive(base_name="__archive__", format="zip", root_dir=work_dir)
        os.replace("__archive__.zip", rebuilt_zip)

        # --- конвертация в PDF через LibreOffice ---
        if job_id:
            setp(job_id, 80, "Конвертация в PDF...")

        # soffice должен быть установлен в образе (у вас уже так)
        subprocess.run([
            "soffice", "--headless",
            "--convert-to", "pdf",
            "--outdir", OUTPUT_DIR,
            rebuilt_zip
        ], check=True)

        pdf_path = rebuilt_zip.replace(".pptx", ".pdf")
        # по желанию удаляем промежуточный pptx
        if os.path.exists(rebuilt_zip):
            os.remove(rebuilt_zip)

        if job_id:
            setp(job_id, 100, "Готово")
            setfile(job_id, pdf_path)

        return pdf_path

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

# -----------------------------
# Эндпойнты
# -----------------------------
@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    # Нужен простой ответ на GET / для ручной проверки
    return HTMLResponse("<h3>Kuvertki generator is up</h3>")

@app.head("/")
def root_head():
    # Для UptimeRobot (HEAD /)
    return PlainTextResponse("", status_code=200)

@app.get("/health")
def health():
    return {"status": "ok"}

# ----- Старый совместимый способ (сразу отдаёт файл) -----
@app.post("/generate")
def generate_compat(name: str = Form(...)):
    names = [x.strip() for x in name.split(",") if x.strip()]
    pdf_path = generate_pdf(names, job_id=None)
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename="кувертки.pdf"
    )

# ----- Новый потоковый способ с прогрессом -----
@app.post("/start")
def start(name: str = Form(...)):
    job_id = uuid.uuid4().hex
    setp(job_id, 1, "Старт")
    names = [x.strip() for x in name.split(",") if x.strip()]

    def worker():
        try:
            generate_pdf(names, job_id=job_id)
        except Exception as e:
            setp(job_id, -1, f"Ошибка: {e}")

    Thread(target=worker, daemon=True).start()
    return {"job_id": job_id}

@app.get("/progress/{job_id}")
def progress(job_id: str):
    return JSONResponse(get_state(job_id))

@app.get("/download/{job_id}")
def download(job_id: str):
    state = get_state(job_id)
    file_path = state.get("file")
    if not file_path or not os.path.exists(file_path):
        return PlainTextResponse("Файл ещё не готов", status_code=404)

    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename="кувертки.pdf"
    )

# Локальный запуск
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
