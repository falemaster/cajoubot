# Dockerfile simplifié pour Railway - Bot Telegram Comptables
FROM python:3.11-slim

# Variables d'environnement pour Python
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Installe les dépendances système
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Crée un utilisateur non-root
RUN useradd --create-home --shell /bin/bash app

# Définit le répertoire de travail
WORKDIR /app

# Copie et installe les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie le code de l'application
COPY . .

# Change vers l'utilisateur non-root
USER app

# Expose le port par défaut
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

# Commande par défaut (bot simplifié)
CMD ["python", "app_simple.py"]

# Labels pour la métadonnée
LABEL maintainer="Nadav"
LABEL description="Bot Telegram pour la gestion des comptables dans Notion"
LABEL version="1.0.0"

