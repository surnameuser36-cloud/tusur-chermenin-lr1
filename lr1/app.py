import hashlib
import os
import random
import re
from datetime import date

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from flask import Flask, make_response, render_template, request, session, url_for
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from PIL import Image
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
from wtforms import IntegerField, SelectField, SubmitField
from wtforms.validators import DataRequired

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VERIFY_TOKEN = "TUSUR-CHERMENIN-20261123-F6FD0817"

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "development-secret-key-change-in-production"
)
app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "static", "images")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max

# Убедимся, что папка для загрузок существует
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Направления склейки
STITCH_DIRECTIONS = [
    ("horizontal", "По горизонтали (бок о бок)"),
    ("vertical", "По вертикали (друг над другом)"),
]


def generate_captcha():
    """Генерирует простую математическую задачу для CAPTCHA"""
    operations = [
        ("+", lambda a, b: a + b),
        ("-", lambda a, b: a - b),
        ("*", lambda a, b: a * b),
    ]
    op_symbol, op_func = random.choice(operations)

    if op_symbol == "*":
        a = random.randint(2, 10)
        b = random.randint(2, 10)
    elif op_symbol == "-":
        a = random.randint(10, 50)
        b = random.randint(1, a)
    else:
        a = random.randint(10, 50)
        b = random.randint(10, 50)

    answer = op_func(a, b)
    question = f"{a} {op_symbol} {b} = ?"

    return question, answer


class ImageStitchForm(FlaskForm):
    image1 = FileField(
        "Первое изображение",
        validators=[
            FileRequired(message="Выберите первое изображение"),
            FileAllowed(["jpg", "png", "jpeg"], "Только изображения (jpg, png, jpeg)!"),
        ],
    )
    image2 = FileField(
        "Второе изображение",
        validators=[
            FileRequired(message="Выберите второе изображение"),
            FileAllowed(["jpg", "png", "jpeg"], "Только изображения (jpg, png, jpeg)!"),
        ],
    )
    direction = SelectField(
        "Направление склейки",
        choices=[(val, label) for val, label in STITCH_DIRECTIONS],
        default="horizontal",
    )
    captcha_answer = IntegerField(
        "Ответ на задачу", validators=[DataRequired(message="Введите ответ на задачу")]
    )
    submit = SubmitField("Склеить изображения")


def stitch_images(image1_path, image2_path, direction):
    """
    Склеивает два изображения по горизонтали или вертикали.
    Изображения масштабируются для совпадения размеров по общей стороне.
    """
    if direction not in {"horizontal", "vertical"}:
        raise ValueError("Направление должно быть horizontal или vertical")

    with Image.open(image1_path) as source1:
        img1 = source1.convert("RGB")
    with Image.open(image2_path) as source2:
        img2 = source2.convert("RGB")

    if direction == "horizontal":
        # Склейка по горизонтали: выравниваем по высоте
        target_height = min(img1.height, img2.height)
        # Масштабируем оба изображения пропорционально
        ratio1 = target_height / img1.height
        img1 = img1.resize((int(img1.width * ratio1), target_height), Image.LANCZOS)
        ratio2 = target_height / img2.height
        img2 = img2.resize((int(img2.width * ratio2), target_height), Image.LANCZOS)

        # Создаём новое изображение
        new_width = img1.width + img2.width
        result = Image.new("RGB", (new_width, target_height))
        result.paste(img1, (0, 0))
        result.paste(img2, (img1.width, 0))
    else:
        # Склейка по вертикали: выравниваем по ширине
        target_width = min(img1.width, img2.width)
        ratio1 = target_width / img1.width
        img1 = img1.resize((target_width, int(img1.height * ratio1)), Image.LANCZOS)
        ratio2 = target_width / img2.width
        img2 = img2.resize((target_width, int(img2.height * ratio2)), Image.LANCZOS)

        # Создаём новое изображение
        new_height = img1.height + img2.height
        result = Image.new("RGB", (target_width, new_height))
        result.paste(img1, (0, 0))
        result.paste(img2, (0, img1.height))

    return result, img1, img2


def plot_color_distribution(image, title, filename):
    """
    Строит гистограмму распределения цветов RGB для изображения.
    """
    img_array = np.array(image.convert("RGB"))

    r = img_array[:, :, 0].flatten()
    g = img_array[:, :, 1].flatten()
    b = img_array[:, :, 2].flatten()

    plt.figure(figsize=(8, 4))
    plt.hist(r, bins=256, color="red", alpha=0.5, label="R")
    plt.hist(g, bins=256, color="green", alpha=0.5, label="G")
    plt.hist(b, bins=256, color="blue", alpha=0.5, label="B")
    plt.legend()
    plt.title(title)
    plt.xlabel("Значение (0-255)")
    plt.ylabel("Частота")
    plt.grid(True, alpha=0.3)

    plot_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    plt.savefig(plot_path, dpi=100, bbox_inches="tight")
    plt.close()

    return plot_path


def clear_old_files():
    """Очищает старые файлы из папки uploads"""
    folder = app.config["UPLOAD_FOLDER"]
    for filename in os.listdir(folder):
        if filename.startswith(("uploaded_", "stitched_", "plot_")):
            try:
                os.remove(os.path.join(folder, filename))
            except OSError:
                pass


def normalize_html(html):
    """Приводит HTML к каноническому виду для вычисления SHA-256."""
    lines = [line.strip() for line in html.split("\n")]
    lines = [line for line in lines if line]
    lines = [re.sub(r"\s+", " ", line) for line in lines]
    return "\n".join(lines)


@app.route("/verify", methods=["GET"])
def verify():
    """Возвращает токен, дату и хэш нормализованного HTML-тела."""
    today = date.today().isoformat()
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"><title>Verification</title></head>
<body>
<h1>Verification</h1>
<p>Token: {VERIFY_TOKEN}</p>
<p>Date: {today}</p>
</body>
</html>"""
    normalized = normalize_html(html)
    body_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    response = make_response(html, 200)
    response.headers["X-Verify-Hash"] = body_hash
    return response


@app.route("/health", methods=["GET"])
def health():
    """Возвращает состояние приложения для проверки хостингом."""
    return {"status": "ok"}, 200


@app.route("/", methods=["GET", "POST"])
def index():
    form = ImageStitchForm()

    # Генерируем новую CAPTCHA если её нет в сессии
    if "captcha_answer" not in session:
        question, answer = generate_captcha()
        session["captcha_question"] = question
        session["captcha_answer"] = answer

    captcha_question = session.get("captcha_question", "")
    captcha_error = None

    if form.validate_on_submit():
        # Проверка CAPTCHA
        user_answer = form.captcha_answer.data
        correct_answer = session.get("captcha_answer")

        if user_answer != correct_answer:
            captcha_error = "Неверный ответ на задачу. Попробуйте ещё раз."
            # Генерируем новую задачу
            question, answer = generate_captcha()
            session["captcha_question"] = question
            session["captcha_answer"] = answer
            captcha_question = question
            return render_template(
                "index.html",
                form=form,
                captcha_question=captcha_question,
                captcha_error=captcha_error,
            )

        # Очищаем старые файлы
        clear_old_files()

        # Сохраняем первое загруженное изображение
        file1 = form.image1.data
        filename1 = "uploaded_1_" + secure_filename(file1.filename)
        path1 = os.path.join(app.config["UPLOAD_FOLDER"], filename1)
        file1.save(path1)

        # Сохраняем второе загруженное изображение
        file2 = form.image2.data
        filename2 = "uploaded_2_" + secure_filename(file2.filename)
        path2 = os.path.join(app.config["UPLOAD_FOLDER"], filename2)
        file2.save(path2)

        # Получаем направление склейки
        direction = form.direction.data

        # Склеиваем изображения
        stitched_img, img1_resized, img2_resized = stitch_images(path1, path2, direction)

        # Сохраняем результат
        stitched_filename = "stitched_result.png"
        stitched_path = os.path.join(app.config["UPLOAD_FOLDER"], stitched_filename)
        stitched_img.save(stitched_path)

        # Создаём графики распределения цветов
        plot_dist1 = plot_color_distribution(
            Image.open(path1),
            "Распределение цветов (изображение 1)",
            "plot_distribution_1.png",
        )
        plot_dist2 = plot_color_distribution(
            Image.open(path2),
            "Распределение цветов (изображение 2)",
            "plot_distribution_2.png",
        )
        plot_dist_result = plot_color_distribution(
            stitched_img,
            "Распределение цветов (результат склейки)",
            "plot_distribution_result.png",
        )

        # Генерируем новую CAPTCHA для следующего запроса
        question, answer = generate_captcha()
        session["captcha_question"] = question
        session["captcha_answer"] = answer

        direction_label = dict(STITCH_DIRECTIONS).get(direction, direction)

        return render_template(
            "index.html",
            form=form,
            image1=url_for("static", filename=f"images/{filename1}"),
            image2=url_for("static", filename=f"images/{filename2}"),
            stitched_image=url_for(
                "static", filename=f"images/{stitched_filename}"
            ),
            direction=direction,
            direction_label=direction_label,
            plot_dist1=url_for(
                "static", filename=f"images/{os.path.basename(plot_dist1)}"
            ),
            plot_dist2=url_for(
                "static", filename=f"images/{os.path.basename(plot_dist2)}"
            ),
            plot_dist_result=url_for(
                "static", filename=f"images/{os.path.basename(plot_dist_result)}"
            ),
            captcha_question=question,
        )

    return render_template(
        "index.html",
        form=form,
        captcha_question=captcha_question,
        captcha_error=captcha_error,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(debug=False, host="0.0.0.0", port=port, use_reloader=False)
