from fastapi import FastAPI, Form
from fastapi.responses import FileResponse, HTMLResponse, Response
import os
import uuid
import subprocess
import logging
import zipfile
import shutil
import re

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kuvertki")


@app.head("/")
def head_root():
    return Response(status_code=200)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def form():
    return """
    <h2>Введите имя или несколько имён через запятую</h2>
    <form action="/generate" method="post">
        <input type="text" name="name" placeholder="Арман, Ержан" style="padding: 8px; width: 250px;">
        <button type="submit" style="padding: 8px 12px; margin-left: 10px;">Создать PDF</button>
    </form>
    """


@app.post("/generate")
def generate(name: str = Form(...)):
    names = [n.strip() for n in name.split(",") if n.strip()]
    if not names:
        return HTMLResponse(content="Введите хотя бы одно имя", status_code=400)

    os.makedirs("output", exist_ok=True)
    uid = uuid.uuid4().hex
    template_dir = f"temp_{uid}"

    logger.info("📦 Распаковка template.pptx...")
    with zipfile.ZipFile("template.pptx", 'r') as zip_ref:
        zip_ref.extractall(template_dir)

    with open(f"{template_dir}/ppt/slides/slide1.xml", "r", encoding="utf-8") as f:
        slide_xml = f.read()

    slide_filenames = []
    for i, person in enumerate(names, 1):
        slide_name = f"slide{i}.xml"
        new_xml = slide_xml

        # Подбор размера шрифта
        base_size = 5600  # = 56pt
        min_size = 3200   # = 32pt
        length = len(person)
        if length <= 10:
            font_size = base_size
        elif length <= 15:
            font_size = base_size - 800
        elif length <= 20:
            font_size = base_size - 1600
        else:
            font_size = min_size

        # Заменяем {{ name }} на XML-блок с жирным текстом и нужным шрифтом
        name_run = (
            f'<a:r>'
            f'<a:rPr lang="ru-RU" dirty="0" smtClean="0" b="1" sz="{font_size}"/>'
            f'<a:t>{person}</a:t>'
            f'</a:r>'
        )
        new_xml = new_xml.replace("{{ name }}", name_run)

        # Жирный текст под QR
        new_xml = re.sub(
            r'(<a:t>(eyacademycca\.com|EY Academy of Business CCA|ey\.academy\.cca|eyacademycca)</a:t>)',
            r'<a:r><a:rPr lang="en-US" dirty="0" smtClean="0" b="1"/>\1</a:r>', new_xml
        )

        # Жирный "Следите за нашими новостями:"
        new_xml = re.sub(
            r'(<a:t>Следите за нашими новостями:</a:t>)',
            r'<a:r><a:rPr lang="ru-RU" dirty="0" smtClean="0" b="1"/>\1</a:r>', new_xml
        )

        with open(f"{template_dir}/ppt/slides/{slide_name}", "w", encoding="utf-8") as f:
            f.write(new_xml)
        slide_filenames.append(slide_name)

    # Обновляем presentation.xml
    pres_path = f"{template_dir}/ppt/presentation.xml"
    with open(pres_path, "r", encoding="utf-8") as f:
        pres_xml = f.read()

    pres_xml = re.sub(r"<p:sldIdLst>.*?</p:sldIdLst>", "", pres_xml, flags=re.DOTALL)
    sldId_entries = "\n".join([
        f'<p:sldId id="{256+i}" r:id="rId{i+1}"/>' for i in range(len(names))
    ])
    sldIdLst = f"<p:sldIdLst>\n{sldId_entries}\n</p:sldIdLst>"
    pres_xml = pres_xml.replace("</p:presentation>", f"{sldIdLst}\n</p:presentation>")

    with open(pres_path, "w", encoding="utf-8") as f:
        f.write(pres_xml)

    # Обновляем presentation.xml.rels
    rels_path = f"{template_dir}/ppt/_rels/presentation.xml.rels"
    with open(rels_path, "r", encoding="utf-8") as f:
        rels_xml = f.read()

    rels_xml = re.sub(r"<Relationships.*?</Relationships>", "", rels_xml, flags=re.DOTALL)
    entries = "\n".join([
        f'<Relationship Id="rId{i+1}" '
        f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
        f'Target="slides/{slide_filenames[i]}"/>' for i in range(len(names))
    ])
    rels_xml = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        f'{entries}\n</Relationships>'
    )

    with open(rels_path, "w", encoding="utf-8") as f:
        f.write(rels_xml)

    # Копируем slide1.xml.rels -> slideN.xml.rels
    for i in range(1, len(names)):
        shutil.copyfile(f"{template_dir}/ppt/slides/_rels/slide1.xml.rels",
                        f"{template_dir}/ppt/slides/_rels/slide{i+1}.xml.rels")

    # Создаём новый PPTX
    pptx_path = f"output/{uid}.pptx"
    shutil.make_archive("archive", 'zip', template_dir)
    os.rename("archive.zip", pptx_path)
    shutil.rmtree(template_dir)

    # Конвертация в PDF через LibreOffice
    logger.info("📎 Конвертация в PDF через LibreOffice...")
    try:
        subprocess.run([
            "soffice", "--headless", "--convert-to", "pdf",
            "--outdir", "output", pptx_path
        ], check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Ошибка при конвертации PDF: {e}")
        return HTMLResponse(content="Ошибка при конвертации PDF", status_code=500)

    pdf_path = pptx_path.replace(".pptx", ".pdf")
    os.remove(pptx_path)
    logger.info("✅ PDF готов и возвращается пользователю.")
    return FileResponse(pdf_path, filename="кувертки.pdf", media_type="application/pdf")
