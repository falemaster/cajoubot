"""
Module de validation et normalisation des données pour le bot Telegram Comptables.

Ce module fournit des fonctions pour valider et normaliser les emails et numéros de téléphone
selon les règles définies dans le brief.
"""

import logging
import re
from typing import Optional, Tuple

import phonenumbers
from email_validator import EmailNotValidError, validate_email
from phonenumbers import NumberParseException

logger = logging.getLogger(__name__)


def validate_and_normalize_email(email: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Valide et normalise une adresse email.
    
    Args:
        email: L'adresse email à valider
        
    Returns:
        Tuple contenant:
        - bool: True si l'email est valide
        - str|None: L'email normalisé (casse corrigée) si valide, None sinon
        - str|None: Message d'erreur si invalide, None sinon
    """
    if not email or email.strip() == "" or email.strip() == "-":
        return True, None, None
    
    email = email.strip()
    
    try:
        # Validation RFC avec normalisation de la casse
        validated_email = validate_email(email)
        normalized_email = validated_email.email
        logger.info(f"Email validé et normalisé: {email} -> {normalized_email}")
        return True, normalized_email, None
    except EmailNotValidError as e:
        error_msg = f"Email invalide: {str(e)}"
        logger.warning(f"Validation email échouée pour '{email}': {error_msg}")
        return False, None, error_msg


def validate_and_normalize_phone(phone: str, default_region: str = "FR") -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Valide et normalise un numéro de téléphone au format E.164.
    
    Args:
        phone: Le numéro de téléphone à valider
        default_region: La région par défaut (ex: "FR", "IL")
        
    Returns:
        Tuple contenant:
        - bool: True si le numéro est valide ou vide
        - str|None: Le numéro normalisé en E.164 si valide, None si vide
        - str|None: Message d'avertissement si le numéro ne peut pas être normalisé
    """
    if not phone or phone.strip() == "" or phone.strip() == "-":
        return True, None, None
    
    phone = phone.strip()
    
    try:
        # Parse le numéro avec la région par défaut
        parsed_number = phonenumbers.parse(phone, default_region)
        
        # Vérifie si le numéro est valide
        if phonenumbers.is_valid_number(parsed_number):
            # Formate en E.164
            normalized_phone = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
            logger.info(f"Téléphone validé et normalisé: {phone} -> {normalized_phone}")
            return True, normalized_phone, None
        else:
            # Numéro invalide mais on le conserve tel quel avec un avertissement
            warning_msg = f"Numéro de téléphone invalide mais conservé: {phone}"
            logger.warning(warning_msg)
            return True, phone, warning_msg
            
    except NumberParseException as e:
        # Erreur de parsing, on conserve tel quel avec un avertissement
        warning_msg = f"Impossible de parser le numéro de téléphone, conservé tel quel: {phone} (erreur: {str(e)})"
        logger.warning(warning_msg)
        return True, phone, warning_msg


def sanitize_text_field(text: str, max_length: Optional[int] = None) -> Optional[str]:
    """
    Nettoie et tronque un champ texte si nécessaire.
    
    Args:
        text: Le texte à nettoyer
        max_length: Longueur maximale (optionnel)
        
    Returns:
        Le texte nettoyé et tronqué, ou None si vide
    """
    if not text or text.strip() == "" or text.strip() == "-":
        return None
    
    cleaned_text = text.strip()
    
    if max_length and len(cleaned_text) > max_length:
        cleaned_text = cleaned_text[:max_length].rstrip()
        logger.info(f"Texte tronqué à {max_length} caractères")
    
    return cleaned_text


def validate_required_field(field_value: str, field_name: str) -> Tuple[bool, Optional[str]]:
    """
    Valide qu'un champ obligatoire n'est pas vide.
    
    Args:
        field_value: La valeur du champ
        field_name: Le nom du champ pour les messages d'erreur
        
    Returns:
        Tuple contenant:
        - bool: True si le champ est valide
        - str|None: Message d'erreur si invalide
    """
    if not field_value or field_value.strip() == "":
        return False, f"Le champ '{field_name}' est obligatoire."
    
    return True, None


# Constantes pour les limites Notion (approximatives)
NOTION_TITLE_MAX_LENGTH = 2000
NOTION_TEXT_MAX_LENGTH = 2000
NOTION_EMAIL_MAX_LENGTH = 200
NOTION_PHONE_MAX_LENGTH = 50

