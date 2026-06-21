# Imagen ligera de Python.
FROM python:3.12-slim

# No generar .pyc y mostrar logs sin buffer.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias primero para aprovechar la cache de capas.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del servidor.
COPY app/ ./app/

# Correr como usuario no-root.
RUN useradd --create-home --uid 1000 appuser
USER appuser

# Puerto por defecto (informativo; el real lo define la variable PORT).
EXPOSE 8000

# Arranca el servidor MCP con transporte streamable-http.
CMD ["python", "-m", "app.server"]
