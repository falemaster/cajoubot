# Dockerfile multi-stage pour le bot Telegram Comptables
# Stage 1: Build dependencies
FROM python:3.11-slim as builder

# Variables d'environnement pour Python
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Installe les dépendances système nécessaires pour la compilation
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Crée un utilisateur non-root
RUN useradd --create-home --shell /bin/bash app

# Définit le répertoire de travail
WORKDIR /app

# Copie et installe les dépendances Python
COPY requirements.txt .
RUN pip install --user --no-warn-script-location -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim as runtime

# Variables d'environnement pour Python
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/home/app/.local/bin:$PATH"

# Installe les dépendances runtime minimales
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Crée un utilisateur non-root
RUN useradd --create-home --shell /bin/bash app

# Copie les dépendances Python depuis le stage builder
COPY --from=builder /home/app/.local /home/app/.local

# Définit le répertoire de travail
WORKDIR /app

# Copie le code de l'application
COPY --chown=app:app . .

# Change vers l'utilisateur non-root
USER app

# Expose le port par défaut
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

# Commande par défaut (mode webhook)
CMD ["python", "app.py"]

# Labels pour la métadonnée
LABEL maintainer="Nadav"
LABEL description="Bot Telegram pour la gestion des comptables dans Notion"
LABEL version="1.0.0"

